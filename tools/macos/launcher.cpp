#include <mach-o/dyld.h>
#include <unistd.h>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
int main(int argc, char** argv) {
    try {
        uint32_t size = 0;
        _NSGetExecutablePath(nullptr, &size);
        std::vector<char> path(size);
        if (_NSGetExecutablePath(path.data(), &size) != 0) return 1;
        const auto binary = std::filesystem::canonical(path.data()).parent_path() / "data2g-gui";
        std::vector<std::string> args{binary.string()};
        bool config = false;
        for (int i = 1; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--config" || arg.rfind("--config=", 0) == 0) config = true;
        }
        if (!config) {
            const char* home = std::getenv("HOME");
            if (!home || !*home) throw std::runtime_error("HOME is not set");
            auto file = std::filesystem::path(home) / "Library/Application Support/Data2G macOS/data2g.conf";
            std::filesystem::create_directories(file.parent_path());
            args.insert(args.end(), {"--config", file.string()});
        }
        for (int i = 1; i < argc; ++i) args.emplace_back(argv[i]);
        std::vector<char*> values;
        for (auto& arg : args) values.push_back(arg.data());
        values.push_back(nullptr);
        execv(binary.c_str(), values.data());
        perror("Data2G macOS");
    } catch (const std::exception& e) { std::cerr << "Data2G macOS: " << e.what() << '\n'; }
    return 1;
}
