// Finding a CM108 sound interface's hidraw device (rig/cm108.hpp), against
// a sysfs tree built in a temporary directory: no device, no libhamlib.

#include <filesystem>
#include <fstream>
#include <string>

#include "check.hpp"
#include "rig/backend.hpp"
#include "rig/cm108.hpp"

using namespace data2g;
namespace fs = std::filesystem;

namespace {

// <root>/class/hidraw/<name>/device/uevent, as the kernel writes it.
void add_hidraw(const fs::path& root, const std::string& name, const std::string& hid_id, const std::string& hid_name) {
    const fs::path dir = root / "class" / "hidraw" / name / "device";
    fs::create_directories(dir);
    std::ofstream(dir / "uevent") << "DRIVER=hid-generic\nHID_ID=" << hid_id << "\nHID_NAME=" << hid_name
                                  << "\nHID_PHYS=usb-0000:00:14.0-2/input3\n";
}

fs::path fresh_root(const std::string& name) {
    const fs::path root = fs::temp_directory_path() / ("data2g-test-cm108-" + name);
    fs::remove_all(root);
    fs::create_directories(root);
    return root;
}

std::string error_of(const std::string& configured, const fs::path& root) {
    try {
        rig::resolve_cm108_device(configured, root.string());
    } catch (const rig::RigError& e) {
        return e.what();
    }
    return {};
}

void test_ids() {
    check::current_step = "ids";
    check::is_true(rig::is_cm108(0x0d8c, 0x000c) && rig::is_cm108(0x0d8c, 0x013c) && rig::is_cm108(0x0d8c, 0x0012),
                   "C-Media CM108, CM119B, CM119");
    check::is_true(rig::is_cm108(0x0c76, 0x1607), "SSS1623");
    check::is_true(!rig::is_cm108(0x0d8c, 0x0014) && !rig::is_cm108(0x046d, 0xc52b), "others: not a CM108 (Hamlib refuses them)");
}

void test_find() {
    check::current_step = "find";
    const fs::path root = fresh_root("find");
    check::is_true(rig::find_cm108_devices(root.string()).empty(), "no hidraw class: none");
    add_hidraw(root, "hidraw0", "0003:0000046D:0000C52B", "Logitech USB Receiver");
    add_hidraw(root, "hidraw10", "0003:00000D8C:00000012", "C-Media Electronics Inc. USB Audio Device");
    add_hidraw(root, "hidraw2", "0003:00000D8C:0000013C", "C-Media Electronics Inc. USB PnP Sound Device");
    fs::create_directories(root / "class" / "hidraw" / "hidraw3" / "device");  // no uevent: skipped
    const auto found = rig::find_cm108_devices(root.string());
    check::equal(found.size(), std::size_t{2}, "two CM108s, the receiver left out");
    if (found.size() == 2) {
        check::equal(found[0].path, std::string("/dev/hidraw2"), "hidraw order: 2 before 10");
        check::equal(found[1].path, std::string("/dev/hidraw10"), "...then 10");
        check::equal(found[0].name, std::string("C-Media Electronics Inc. USB PnP Sound Device"), "HID_NAME read");
        check::is_true(found[0].vendor == 0x0d8c && found[0].product == 0x013c, "ids parsed as hex");
    }
    fs::remove_all(root);
}

void test_resolve() {
    check::current_step = "resolve";
    const fs::path root = fresh_root("resolve");
    check::equal(rig::resolve_cm108_device("/dev/hidraw7", root.string()), std::string("/dev/hidraw7"), "a given device is kept");
    check::is_true(error_of("", root).find("no CM108") != std::string::npos, "none plugged in: says so");
    add_hidraw(root, "hidraw1", "0003:00000D8C:0000000C", "C-Media Electronics Inc. USB Audio Device");
    check::equal(rig::resolve_cm108_device("", root.string()), std::string("/dev/hidraw1"), "one plugged in: that one");
    add_hidraw(root, "hidraw4", "0003:00000D8C:0000013A", "TOADs DI");
    const std::string two = error_of("", root);
    check::is_true(two.find("/dev/hidraw1") != std::string::npos && two.find("/dev/hidraw4 (TOADs DI)") != std::string::npos,
                   "two plugged in: both named: " + two);
    fs::remove_all(root);
}

}  // namespace

int main() {
    test_ids();
    test_find();
    test_resolve();
    return check::report("rig_cm108");
}
