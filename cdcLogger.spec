# -*- mode: python -*-
a = Analysis(['cdcLogger/cdcLogger.pyw'],
             pathex=['C:\\Users\\Kim\\Desktop\\pyinstaller-2.0'],
             hiddenimports=[],
             hookspath=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('dist', 'cdcLogger.exe'),
          debug=False,
          strip=None,
          upx=True,
          console=False )
app = BUNDLE(exe,
             name=os.path.join('dist', 'cdcLogger.exe.app'))
