#!/usr/bin/env python3
"""Stage the N4EAC macOS app, with its own preferences and bundled dependencies."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess
import urllib.request

root = Path(__file__).resolve().parents[2]
tools = root / 'tools/macos'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
parser.add_argument('--stage', required=True, type=Path)
a = parser.parse_args()
build, stage = a.build.resolve(), a.stage.resolve()
app = stage / 'Data2G.app'
if app.exists():
    parser.error('Use an empty staging directory; an app already exists there')

def run(*args):
    subprocess.run([str(x) for x in args], check=True)

def output(*args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()

def brew(name):
    return Path(output('brew', '--prefix', name))

qt, svg, websockets = brew('qtbase'), brew('qtsvg'), brew('qtwebsockets')
run('ditto', build/'data2g-gui.app', app)
bin_dir, res = app/'Contents/MacOS', app/'Contents/Resources'
for name in ('data2g-host', 'data2g-web', 'data2g-monitor', 'data2g-audio-check'):
    shutil.copy2(build/name, bin_dir/name)
for kind, names in {'platforms':('libqcocoa.dylib','libqoffscreen.dylib'),
                    'imageformats':('libqgif.dylib','libqico.dylib','libqjpeg.dylib'),
                    'styles':('libqmacstyle.dylib',)}.items():
    dest = app/'Contents/PlugIns'/kind
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(qt/'share/qt/plugins'/kind/name, dest/name)
shutil.copy2(svg/'share/qt/plugins/imageformats/libqsvg.dylib', app/'Contents/PlugIns/imageformats/libqsvg.dylib')
run('ditto', svg/'lib/QtSvg.framework', app/'Contents/Frameworks/QtSvg.framework')
extra = ['-executable='+str(p) for p in sorted(bin_dir.iterdir())]
extra += ['-executable='+str(p) for p in sorted((app/'Contents/PlugIns').rglob('*.dylib'))]
run(qt/'bin/macdeployqt', app, '-no-plugins', '-always-overwrite',
    '-libpath='+str(qt/'lib'), '-libpath='+str(svg/'lib'), '-libpath='+str(websockets/'lib'), *extra)
run('python3', tools/'normalize-libraries.py', app)
run('c++', '-std=c++17', '-O2', '-arch', 'arm64', '-mmacosx-version-min=27.0',
    tools/'launcher.cpp', '-o', bin_dir/'data2g-launcher')
p = app/'Contents/Info.plist'
info = plistlib.loads(p.read_bytes())
info.update(CFBundleExecutable='data2g-launcher', CFBundleIdentifier='io.github.n4eac.data2g',
            CFBundleName='Data2G', CFBundleDisplayName='Data2G')
p.write_bytes(plistlib.dumps(info))
(res/'qt.conf').write_text('[Paths]\nPlugins = PlugIns\n')
revision = output('git', '-C', root, 'rev-parse', 'HEAD')
engine = '95c94b1c1b85edbdff6d1e6828d3087e67ccfeef'
qt_version = output(qt/'bin/qmake', '-query', 'QT_VERSION')
(res/'Data2G-revision.txt').write_text(revision+'\n')
(res/'BuildInfo.txt').write_text(f'Data2G 0.5.3 + HF upstream fixes\nPackaging revision: {revision}\nUpstream engine base: {engine}\nProfile: HF, protocol 15\nArchitecture: arm64\nMinimum macOS: 27.0\nQt: {qt_version}\nSource: https://github.com/N4EAC/Data2G\nSettings: ~/Library/Application Support/Data2G macOS/data2g.conf\nAd hoc signed; not notarized.\n')
licenses = res/'Licenses'
licenses.mkdir(exist_ok=True)
for name in ('LICENSE','LICENSE_exception','LICENSE_ion'):
    shutil.copy2(root/name, licenses/('Data2G-'+name+'.txt'))
for name in ('miniaudio','pocketfft'):
    shutil.copy2(root/'native/third_party'/name/'LICENSE', licenses/(name+'.txt'))
shutil.copy2(brew('hamlib')/'COPYING.LIB', licenses/'Hamlib.txt')
for name in ('LGPL-3.0-only','GPL-3.0-only','Qt-GPL-exception-1.0'):
    with urllib.request.urlopen(f'https://raw.githubusercontent.com/qt/qtbase/v{qt_version}/LICENSES/{name}.txt') as reply:
        (licenses/(name+'.txt')).write_bytes(reply.read())
run('codesign', '--force', '--deep', '--sign', '-', '--entitlements', root/'native/packaging/data2g.entitlements', app)
run('python3', tools/'verify-package.py', app)
print(app)
