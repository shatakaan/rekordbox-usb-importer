# dmgbuild settings for PlaylistConverter
# Usage: dmgbuild -s build/dmgbuild_settings.py -D app=dist/PlaylistConverter.app "Playlist Converter" dist/PlaylistConverter-1.0.0.dmg

application = defines.get('app', '../dist/PlaylistConverter.app')
appname = 'PlaylistConverter'

files = [application]
symlinks = {'Applications': '/Applications'}

icon_locations = {
    'PlaylistConverter.app': (150, 160),
    'Applications': (350, 160),
}

background = 'builtin-arrow'
window_rect = ((100, 100), (500, 320))
icon_size = 80
text_size = 12
format = 'UDZO'
