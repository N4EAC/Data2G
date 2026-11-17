// Finding the HID device of a CM108-family USB sound chip, for PTT on one
// of its GPIO pins (PttMethod::Cm108). Hamlib keys the pin once it has the
// device's path; what it cannot do is find that path. Its default is
// /dev/hidraw0, which is the keyboard or mouse as often as not.
//
// Linux only, like Hamlib's own CM108 support (its cm108_open is a hidraw
// ioctl): elsewhere find_cm108_devices() is empty. Part of data2g_core and
// needs no libhamlib, so a settings page can list the devices in any build.
#pragma once

#include <string>
#include <vector>

namespace data2g::rig {

struct Cm108Device {
    std::string path;  // /dev/hidraw3
    std::string name;  // HID_NAME: "C-Media Electronics Inc. USB Audio Device"
    unsigned vendor = 0, product = 0;
};

// Whether Hamlib's cm108_open will accept a chip with these USB ids: the
// list in its src/cm108.c (C-Media CM108/108B/109/119/119A/119B and the
// SSS1621/23). Any other device is refused there with -RIG_EINVAL.
bool is_cm108(unsigned vendor, unsigned product);

// Every hidraw device that is a CM108-family chip, in hidraw order.
// `sysfs` is the sysfs mount, for the tests.
std::vector<Cm108Device> find_cm108_devices(const std::string& sysfs = "/sys");

// The device to key: `configured` if it is set, else the one CM108 found.
// Throws RigError when there is none, or more than one to choose from
// (naming them, so the operator can pick).
std::string resolve_cm108_device(const std::string& configured, const std::string& sysfs = "/sys");

}  // namespace data2g::rig
