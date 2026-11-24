from pathlib import Path
import plistlib,re,subprocess,sys
app=Path(sys.argv[1]).resolve()
frameworks=app/'Contents/Frameworks'
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['CFBundleIdentifier']=='io.github.n4eac.data2g'
assert (app/'Contents/PlugIns/platforms/libqcocoa.dylib').is_file()
magic={bytes.fromhex(x) for x in ('cffaedfe','feedfacf','cafebabe','bebafeca')}
seen=set()
for item in app.rglob('*'):
 if not item.is_file(): continue
 path=item.resolve()
 assert path.is_relative_to(app),item
 if path in seen: continue
 with path.open('rb') as f:
  if f.read(4) not in magic: continue
 seen.add(path)
 def out(*args): return subprocess.check_output(args,text=True)
 assert 'arm64' in out('lipo','-archs',str(path)),path
 ids=out('otool','-D',str(path)).splitlines()[1:]
 for load in out('otool','-L',str(path)).splitlines()[1:]:
  dep=load.strip().split(' (',1)[0]
  if dep in ids or dep.startswith(('/System/Library/','/usr/lib/')): continue
  if dep.startswith('@rpath/'): target=frameworks/dep.removeprefix('@rpath/')
  elif dep.startswith('@loader_path/'): target=path.parent/dep.removeprefix('@loader_path/')
  elif dep.startswith('@executable_path/'): target=app/'Contents/MacOS'/dep.removeprefix('@executable_path/')
  else: raise RuntimeError(f'External dependency: {path.name}: {dep}')
  assert target.is_file() and target.resolve().is_relative_to(app),(path,dep,target)
 for rpath in re.findall(r'\bpath (.*?) \(offset \d+\)',out('otool','-l',str(path))):
  assert rpath.startswith(('@loader_path','@executable_path')),(path,rpath)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
print(f'Verified {len(seen)} Mach-O binaries, Cocoa plugin, signatures and all bundled dependencies')
