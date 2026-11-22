// FM ping / level check (data2g/arq/ping.py, normative; FM plan M7): a measurement burst
// for a station's TX path setting and audio level, no session. FM only (frames T_PING).
#pragma once

#include <array>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

#include "arq/frames.hpp"
#include "modem/modem.hpp"

namespace data2g::arq::ping {

// cap (1 NARROW, 2 WIDE) -> the band's ping mode
inline const std::map<int, std::string> PING_MODES = {{1, "f55-qpsk-r21"}, {2, "f108-qpsk-r21"}};
inline constexpr double REPLY_HOLDOFF_S = 10.0;
inline constexpr int REPORT_BYTES = 9;
// verdict thresholds (ping.py: measured on the FM simulator, scripts/fm_ping_study.py)
inline const std::map<std::string, double> DIST_DB = {{"f55", 1.5}, {"f108", 2.5}};
inline constexpr double TILT_DB = 1.0, NOISE_TILT_DB = 1.5, MIN_SNR_DB = 12.0, CLIP_DBFS = -0.1;
// the step pair (ping.py: measured on air, runs/onair/2026-11-22/notes.md, and on the FM simulator)
inline constexpr double STEP_DB = 10.0, HELD_SNR_DB = 2.0, FOLLOW_SLOPE = 0.6, FLAT_SLOPE = 0.2, VARIED_DB = 1.0,
                        DIST_FALL_DB = 0.5, DEAD_THIRD_DB = 15.0;

struct Report {
    double snr_db = 0, rms_dbfs = -64, peak_dbfs = -64;
    int clip_permille = 0;
    std::array<double, 3> thirds_db{};
    double dist_db = 0, noise_tilt_db = 0;
};

double tx_level(std::string_view tx_path);  // the quietest top mode's gain on mic, 1 on flat
std::string fmt(const Report& m);
Bytes ping_body(const std::string& frm, const std::string& to, const std::optional<Bytes>& report, int payload_bytes,
                bool step = false);
// -> (from, to, report if a reply, the step flag); throws std::invalid_argument if malformed
std::tuple<std::string, std::string, std::optional<Bytes>, bool> unpack_ping(ByteView body);
Bytes pack_report(const Report& m);
Report unpack_report(ByteView b);
Report level(std::span<const double> x);  // rms_dbfs, peak_dbfs, clip_permille only
// The sender's transmitter as `r` shows it; `payloads`: its decoded control codewords; `lvl`: level() of its samples.
Report measure(const modem::Received& r, const std::vector<Bytes>& payloads, const Report& lvl);
// One burst's advice (no level line: that waits for the step ping, level_verdict).
std::vector<std::string> verdict(const Report& far, std::string_view tx_path, const std::string& band = "f55");
// The level, from the far end's measurements of the ping and of the step ping STEP_DB under it.
std::string level_verdict(const Report& full, const Report& step, std::string_view tx_path, const std::string& band = "f55");

}  // namespace data2g::arq::ping
