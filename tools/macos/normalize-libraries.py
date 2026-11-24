from pathlib import Path
import re
import subprocess
import sys
app = Path(sys.argv[1]).resolve()
frameworks = app / "Contents/Frameworks"
magic = {bytes.fromhex(x) for x in ("cffaedfe", "feedfacf", "cafebabe", "bebafeca")}
seen = set()
for candidate in app.rglob("*"):
    if not candidate.is_file():
        continue
    binary = candidate.resolve()
    if binary in seen:
        continue
    if not binary.is_relative_to(app):
        raise RuntimeError(f"Library symlink leaves the app: {candidate}")
    with binary.open("rb") as source:
        if source.read(4) not in magic:
            continue
    seen.add(binary)
    install_ids = subprocess.check_output(["otool", "-D", str(binary)], text=True).splitlines()[1:]
    if install_ids:
        relative = binary.relative_to(frameworks) if binary.is_relative_to(frameworks) else None
        if relative:
            subprocess.run(["install_name_tool", "-id", "@rpath/" + str(relative), str(binary)], check=True)
    for line in subprocess.check_output(["otool", "-L", str(binary)], text=True).splitlines()[1:]:
        dependency = line.strip().split(" (", 1)[0]
        if not dependency.startswith("/") or dependency.startswith(("/System/Library/", "/usr/lib/")):
            continue
        relative = dependency.split("/lib/", 1)[-1]
        target = frameworks / relative
        if not target.exists():
            target = frameworks / Path(dependency).name
        if not target.exists() or not target.resolve().is_relative_to(app):
            raise RuntimeError(f"Unbundled dependency in {binary.name}: {dependency}")
        replacement = "@rpath/" + str(target.relative_to(frameworks))
        subprocess.run(["install_name_tool", "-change", dependency, replacement, str(binary)], check=True)
    loads = subprocess.check_output(["otool", "-l", str(binary)], text=True)
    for path in re.findall(r"\bpath (.*?) \(offset \d+\)", loads):
        if path.startswith("/"):
            subprocess.run(["install_name_tool", "-delete_rpath", path, str(binary)], check=True)
