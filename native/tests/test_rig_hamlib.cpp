// The libhamlib backend with no radio: Hamlib's dummy rig (model 1)
// directly, then the host's real path, model 2 (NET rigctl) to a rigctld
// running the dummy, as tnc.Rigctld reaches localhost:4532 today.

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <spawn.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <mutex>
#include <thread>
#include <vector>

#include "audio/fifo.hpp"
#include "check.hpp"
#include "rig/controller.hpp"
#include "rig/hamlib/hamlib.hpp"
#include "rig/keyer.hpp"

extern char** environ;

using namespace data2g;

namespace {

void test_dummy() {
    check::current_step = "dummy";
    rig::HamlibConfig cfg;
    cfg.model = rig::MODEL_DUMMY;
    cfg.device = "";
    auto rig = rig::make_hamlib_backend(cfg);
    rig->open();
    rig->set_ptt(true);
    rig->set_ptt(false);
    check::is_true(rig->frequency_hz() > 0, "dummy: frequency");
    check::is_true(rig->description().find("Dummy") != std::string::npos, "dummy: description " + rig->description());
    rig->close();
    bool threw = false;
    try {
        rig->set_ptt(true);
    } catch (const rig::RigError&) {
        threw = true;
    }
    check::is_true(threw, "closed: PTT reports rather than crashes");
}

// The model list a picker shows, and what it says about port types.
void test_models() {
    check::current_step = "models";
    const auto models = rig::list_models();
    check::is_true(models.size() > 100, "list_models: Hamlib's whole list");
    const auto find = [&](int n) { return std::find_if(models.begin(), models.end(), [n](const rig::RigModel& m) { return m.model == n; }); };
    check::is_true(find(rig::MODEL_DUMMY) != models.end() && find(rig::MODEL_NET_RIGCTL) != models.end(), "dummy and NET rigctl listed");
    const auto dummy = rig::model_info(rig::MODEL_DUMMY);
    const auto net = rig::model_info(rig::MODEL_NET_RIGCTL);
    const auto ic7300 = rig::model_info(3073);
    check::is_true(dummy && dummy->port == rig::PortType::None, "dummy: no port");
    check::is_true(net && net->port == rig::PortType::Network && net->label().find("NET rigctl") != std::string::npos,
                   "model 2: a network port, labelled");
    check::is_true(ic7300 && ic7300->port == rig::PortType::Serial && ic7300->manufacturer == "Icom", "IC-7300: serial");
    check::is_true(!rig::model_info(999999), "an unknown model: nullopt");
    check::is_true(rig::supports_ptt_audio_source(2028) && !rig::supports_ptt_audio_source(rig::MODEL_DUMMY),
                   "mic/data keying: TS-480 yes, dummy no");
}

// Every setting set at once on the dummy (tokens it lacks are skipped), and
// Hamlib's trace through the sink.
void test_dummy_all_settings() {
    check::current_step = "dummy, all settings";
    std::vector<std::string> trace;
    std::mutex m;
    rig::set_debug_sink([&](const std::string& line) {
        std::lock_guard<std::mutex> lock(m);
        trace.push_back(line);
    });
    rig::HamlibConfig cfg;
    cfg.model = rig::MODEL_DUMMY;
    cfg.device = "";
    cfg.baud = 9600;
    cfg.data_bits = rig::DataBits::Eight;
    cfg.stop_bits = rig::StopBits::One;
    cfg.parity = rig::Parity::None;
    cfg.handshake = rig::Handshake::None;
    cfg.dtr = rig::LineState::High;
    cfg.rts = rig::LineState::Low;
    cfg.ptt_method = rig::PttMethod::Cat;
    cfg.ptt_audio = rig::PttAudio::Data;
    cfg.mode = rig::RigMode::PktUsb;
    cfg.timeout_ms = 500;
    cfg.retries = 2;
    auto rig = rig::make_hamlib_backend(cfg);
    rig->open();
    rig->set_ptt(true);
    rig->set_ptt(false);
    check::is_true(rig->frequency_hz() > 0, "all settings: frequency");
    rig->close();
    rig::set_debug_sink({});
    std::lock_guard<std::mutex> lock(m);
    check::is_true(!trace.empty(), "debug sink: Hamlib's trace arrived (" + std::to_string(trace.size()) + " lines)");
    check::is_true(std::none_of(trace.begin(), trace.end(), [](const std::string& l) { return l.find('\n') != std::string::npos; }),
                   "debug sink: a line at a time");
}

// A serial model, configured in full, given a device that does not exist:
// the open fails with a message, nothing else (no serial device is opened).
void test_serial_model_without_a_device() {
    check::current_step = "serial model";
    rig::HamlibConfig cfg;
    cfg.model = 3073;  // IC-7300
    cfg.device = "/nonexistent/data2g-tty";
    cfg.baud = 19200;
    cfg.data_bits = rig::DataBits::Eight;
    cfg.stop_bits = rig::StopBits::Two;
    cfg.parity = rig::Parity::Even;
    cfg.handshake = rig::Handshake::Hardware;
    cfg.ptt_method = rig::PttMethod::Rts;
    cfg.ptt_device = "/nonexistent/data2g-ptt";
    cfg.timeout_ms = 200;
    cfg.retries = 0;
    auto rig = rig::make_hamlib_backend(cfg);
    std::string error;
    try {
        rig->open();
    } catch (const rig::RigError& e) {
        error = e.what();
    }
    check::is_true(!error.empty(), "serial model, no device: open reports (" + error + ")");
    // rigerror() hands back a trace backlog; only the error line belongs here.
    check::is_true(error.find('\n') == std::string::npos, "open error is one line: " + error);
    check::is_true(rig->description().find("IC-7300") != std::string::npos, "description names the model: " + rig->description());
}

// PTT by a CM108's GPIO: Hamlib opens the given hidraw device at rig_open
// and refuses one that isn't there or isn't a CM108, so a dummy rig that
// opens cleanly without it fails here only if the settings reached Hamlib.
void test_cm108() {
    check::current_step = "cm108";
    rig::HamlibConfig cfg;
    cfg.model = rig::MODEL_DUMMY;
    cfg.device = "";
    cfg.ptt_method = rig::PttMethod::Cm108;
    cfg.ptt_device = "/nonexistent/data2g-hidraw";
    cfg.ptt_gpio = 3;
    const auto open_error = [&] {
        auto rig = rig::make_hamlib_backend(cfg);
        try {
            rig->open();
        } catch (const rig::RigError& e) {
            return std::string(e.what());
        }
        return std::string();
    };
    const std::string missing = open_error();
    check::is_true(!missing.empty(), "cm108: a missing hidraw device fails the open");
    check::is_true(missing.find("/nonexistent/data2g-hidraw") != std::string::npos && missing.find("udev") != std::string::npos,
                   "cm108: the error names the device and the likely fix: " + missing);
    check::is_true(missing.find('\n') == std::string::npos, "cm108: one line");
#ifdef __linux__
    // A file that opens but is no hidraw device: Hamlib's CM108 check (a
    // Linux hidraw ioctl; elsewhere it opens any path) refuses it.
    const std::string plain = (std::filesystem::temp_directory_path() / "data2g-test-not-hidraw").string();
    std::fclose(std::fopen(plain.c_str(), "w"));
    cfg.ptt_device = plain;
    check::is_true(!open_error().empty(), "cm108: a device that isn't a CM108 is refused");
    std::remove(plain.c_str());
#endif
    auto rig = rig::make_hamlib_backend(cfg);
    check::is_true(rig->description().find("PTT on GPIO3") != std::string::npos, "description names the pin: " + rig->description());
}

int free_port() {
    const int s = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    bind(s, reinterpret_cast<sockaddr*>(&a), sizeof a);
    socklen_t len = sizeof a;
    getsockname(s, reinterpret_cast<sockaddr*>(&a), &len);
    close(s);
    return ntohs(a.sin_port);
}

bool listening(int port) {
    const int s = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    a.sin_port = htons(static_cast<std::uint16_t>(port));
    const bool ok = connect(s, reinterpret_cast<sockaddr*>(&a), sizeof a) == 0;
    close(s);
    return ok;
}

// The CAT port's speed survives CM108 PTT. Hamlib stores ptt_bitnum over
// the rig port's parm.serial.rate as well as the PTT port's, so a serial
// rig used to open at "2 baud": "Invalid configuration" before the PTT
// port was ever tried. A pty stands in for the G90's CAT cable; the PTT
// device is missing, so getting as far as it proves the serial port opened.
void test_cm108_keeps_cat_baud() {
    check::current_step = "cm108 keeps the CAT baud";
    const int master = posix_openpt(O_RDWR | O_NOCTTY);
    check::is_true(master >= 0 && grantpt(master) == 0 && unlockpt(master) == 0, "a pty for the CAT port");
    if (master < 0) return;
    rig::HamlibConfig cfg;
    cfg.model = 3088;  // Xiegu G90: a serial Icom-protocol rig
    cfg.device = ptsname(master);
    cfg.baud = 19200;
    cfg.timeout_ms = 200;
    cfg.retries = 0;
    cfg.ptt_method = rig::PttMethod::Cm108;
    cfg.ptt_device = "/nonexistent/data2g-hidraw";
    for (const int gpio : {3, 4}) {  // the default pin, and one that moves ptt_bitnum
        cfg.ptt_gpio = gpio;
        std::string error;
        try {
            rig::make_hamlib_backend(cfg)->open();
        } catch (const rig::RigError& e) {
            error = e.what();
        }
        check::is_true(error.find("Invalid configuration") == std::string::npos && error.find("udev") != std::string::npos,
                       "GPIO" + std::to_string(gpio) + ": the serial port opens, then the missing CM108 fails: " + error);
    }
    close(master);
}

// (a) of the exit rule: a rigctld that isn't there (a free port, nothing
// listening). The Keyer's exit sends no PTT off and warns of nothing.
void test_unreachable_rigctld_exit() {
    check::current_step = "unreachable rigctld";
    rig::HamlibConfig cfg;
    cfg.device = "127.0.0.1:" + std::to_string(free_port());
    std::string status;
    bool status_error = false;
    std::mutex m;
    std::condition_variable cv;
    rig::RigController controller({}, [&](const std::string& s, bool error) {
        std::lock_guard<std::mutex> lock(m);
        status = s;
        status_error = error;
        cv.notify_all();
    });
    rig::RigConfig rc;
    rc.poll_interval_s = 0;
    controller.start(rig::make_hamlib_backend(cfg), rc);
    {
        std::unique_lock<std::mutex> lock(m);
        check::is_true(cv.wait_for(lock, std::chrono::seconds(30), [&] { return status_error; }), "open failed: " + status);
    }
    audio::PlaybackFifo fifo(8000, 0.0);
    std::vector<std::string> reports;
    const auto t0 = std::chrono::steady_clock::now();
    {
        rig::Keyer k(controller.ptt_function(), fifo, 0.0, [&](const std::string& s) { reports.push_back(s); },
                     [&] { return controller.keyed_since_open(); });
    }
    const double took = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    check::is_true(reports.empty(), "unreachable: no PTT off warning on exit");
    check::is_true(took < 1.0, "unreachable: exit doesn't wait for a PTT off (" + std::to_string(took) + " s)");
    controller.stop();
    check::is_true(controller.wait_for_shutdown(5.0), "unreachable: worker gone");
}

void test_net_rigctl() {
    check::current_step = "rigctld";
    const std::string rigctld = DATA2G_RIGCTLD;
    if (rigctld.empty() || rigctld.find("NOTFOUND") != std::string::npos) {
        check::fail("rigctld", "not found at configure time");
        return;
    }
    const std::string port = std::to_string(free_port());
    const char* argv[] = {rigctld.c_str(), "-m", "1", "-T", "127.0.0.1", "-t", port.c_str(), nullptr};
    pid_t pid = 0;
    auto spawn = [&] {
        if (posix_spawn(&pid, rigctld.c_str(), nullptr, nullptr, const_cast<char**>(argv), environ) != 0) {
            check::fail("rigctld", "could not start " + rigctld);
            return false;
        }
        for (int i = 0; i < 250 && !listening(std::stoi(port)); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(20));
        // Let rigctld finish with the probe's connection: a client connecting
        // microseconds after the probe closed failed rig_open 5 runs in 6 (short
        // read in dump_state); never when slowed down (strace, or rigctl's startup).
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        return true;
    };
    if (!spawn()) return;

    rig::HamlibConfig cfg;  // the defaults are the host's: model 2
    cfg.device = "127.0.0.1:" + port;
    // The open's dump_state round trip missed the 1 s default about 1 run in
    // 3 on a loaded machine (rigctld just spawned); the default stays for live use.
    cfg.timeout_ms = 5000;
    std::string status;
    std::mutex m;
    rig::RigController controller({}, [&](const std::string& s, bool) {
        std::lock_guard<std::mutex> lock(m);
        status = s;
    });
    rig::RigConfig rc;
    rc.poll_interval_s = 0;
    controller.start(rig::make_hamlib_backend(cfg), rc);
    // (b) of the exit rule: opened, not keyed. The controller opens on its
    // worker; wait for its "Rig: ..." status before asking.
    for (int i = 0; i < 500; ++i) {
        {
            std::lock_guard<std::mutex> lock(m);
            if (status.find("127.0.0.1:" + port) != std::string::npos) break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    check::is_true(!controller.keyed_since_open(), "rigctld: opened, not keyed: exit would send no PTT off");
    bool ok = true;
    try {
        controller.set_ptt(true);
        controller.set_ptt(false);
    } catch (const std::exception& e) {
        ok = false;
        check::fail("rigctld: PTT", e.what());
    }
    check::is_true(ok, "model 2 keys through rigctld");
    check::is_true(controller.keyed_since_open(), "rigctld: keyed: exit sends PTT off");  // (c)
    // A rigctld that dropped us between overs (kappanhang did): the next
    // PTT finds a dead socket, reconnects, and still keys. SIGKILL: SIGTERM
    // left rigctld running (waitpid hung) with our client connected.
    kill(pid, SIGKILL);
    waitpid(pid, nullptr, 0);
    if (!spawn()) return;
    try {
        controller.set_ptt(true);
        controller.set_ptt(false);
    } catch (const std::exception& e) {
        check::fail("rigctld: PTT after a dropped connection", e.what());
    }
    controller.stop();
    check::is_true(controller.wait_for_shutdown(5.0), "rigctld: worker closed the rig");
    {
        std::lock_guard<std::mutex> lock(m);
        check::is_true(status.find("127.0.0.1:" + port) != std::string::npos, "status names the rigctld: " + status);
    }
    kill(pid, SIGTERM);
    waitpid(pid, nullptr, 0);
}

}  // namespace

int main() {
    check::report_crashes_instead_of_prompting();
    check::Watchdog watchdog(100, "test_rig_hamlib");
    std::printf("hamlib %s\n", rig::hamlib_version().c_str());
    test_models();
    test_dummy();
    test_dummy_all_settings();
    test_serial_model_without_a_device();
    test_cm108();
    test_cm108_keeps_cat_baud();
    test_unreachable_rigctld_exit();
    test_net_rigctl();
    return check::report("rig hamlib");
}
