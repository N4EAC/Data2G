#include "rig/cm108.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string_view>
#include <system_error>
#include <utility>

#include "rig/backend.hpp"

namespace data2g::rig {

namespace fs = std::filesystem;

namespace {

// "HID_ID=0003:00000D8C:0000013C": bus, vendor, product, in hex.
bool parse_hid_id(std::string_view value, unsigned& vendor, unsigned& product) {
    const auto first = value.find(':');
    const auto second = first == std::string_view::npos ? first : value.find(':', first + 1);
    if (second == std::string_view::npos) return false;
    const std::string v(value.substr(first + 1, second - first - 1)), p(value.substr(second + 1));
    char* end = nullptr;
    const unsigned long vv = std::strtoul(v.c_str(), &end, 16);
    if (v.empty() || *end != '\0') return false;
    const unsigned long pv = std::strtoul(p.c_str(), &end, 16);
    if (p.empty() || *end != '\0') return false;
    vendor = static_cast<unsigned>(vv);
    product = static_cast<unsigned>(pv);
    return true;
}

// hidraw10 after hidraw9, as /dev lists them.
int hidraw_number(const std::string& name) {
    constexpr std::string_view prefix = "hidraw";
    if (name.rfind(prefix, 0) != 0) return -1;
    return std::atoi(name.c_str() + prefix.size());
}

}  // namespace

bool is_cm108(unsigned vendor, unsigned product) {
    if (vendor == 0x0d8c)
        return (product >= 0x0008 && product <= 0x000f) || product == 0x0012 || product == 0x0013 || product == 0x013a ||
               product == 0x013c;
    if (vendor == 0x0c76) return product == 0x1605 || product == 0x1607 || product == 0x160b;
    return false;
}

std::vector<Cm108Device> find_cm108_devices(const std::string& sysfs) {
    std::vector<Cm108Device> found;
    std::error_code ec;
    const fs::path cls = fs::path(sysfs) / "class" / "hidraw";
    if (!fs::is_directory(cls, ec)) return found;
    std::vector<std::string> names;
    for (const auto& e : fs::directory_iterator(cls, ec)) names.push_back(e.path().filename().string());
    std::sort(names.begin(), names.end(), [](const std::string& a, const std::string& b) {
        return hidraw_number(a) < hidraw_number(b);
    });
    for (const std::string& n : names) {
        std::ifstream uevent(cls / n / "device" / "uevent");
        if (!uevent) continue;
        Cm108Device d;
        bool have_id = false;
        for (std::string line; std::getline(uevent, line);) {
            if (line.rfind("HID_ID=", 0) == 0) have_id = parse_hid_id(std::string_view(line).substr(7), d.vendor, d.product);
            else if (line.rfind("HID_NAME=", 0) == 0) d.name = line.substr(9);
        }
        if (!have_id || !is_cm108(d.vendor, d.product)) continue;
        d.path = "/dev/" + n;
        found.push_back(std::move(d));
    }
    return found;
}

std::string resolve_cm108_device(const std::string& configured, const std::string& sysfs) {
    if (!configured.empty()) return configured;
    const auto found = find_cm108_devices(sysfs);
    if (found.size() == 1) return found.front().path;
    if (found.empty())
        throw RigError("PTT by CM108: no CM108 sound interface found (is it plugged in?); "
                       "give its /dev/hidrawN as the PTT port");
    std::string all;
    for (const auto& d : found) all += (all.empty() ? "" : ", ") + d.path + " (" + d.name + ")";
    throw RigError("PTT by CM108: more than one CM108 sound interface (" + all + "); give the one to key as the PTT port");
}

}  // namespace data2g::rig
