# VHS tape for the keyward demo GIF.
# Render with:  vhs demo/demo.tape   (run from the plugin root)
# Requires: https://github.com/charmbracelet/vhs

Output demo/keyward-demo.gif

Set Shell "bash"
Set FontSize 17
Set Width 1200
Set Height 760
Set Padding 24
Set Theme "Catppuccin Mocha"

Sleep 600ms
Type "KV_DEMO_PAUSE=0.55 python3 demo/demo.py"
Sleep 500ms
Enter
Sleep 15s
