# Linux desktop destination folders

With Use Linux default folders enabled, Home-based automatic sorting and Rule
Tester predictions reuse the folders registered by the Linux desktop. This
supports localized names, symlinks and folders on another drive.

| Classification | Destination |
| --- | --- |
| Images, Pictures, Media/Images | Desktop Pictures folder |
| Videos, Media/Videos | Desktop Videos folder |
| Audio, Music, Media/Audio | Desktop Music folder |
| Documents | Desktop Documents folder |
| College, Work, Code, Projects, Cybersecurity | Category hierarchy beneath Documents |
| Archives, Applications, Others, untyped Media | Category hierarchy beneath Downloads |

Rules beginning with recognized standard-folder prefixes also use those desktop
locations while retaining their remaining path, e.g. Pictures/Low_Quality/PNG.
Explicit custom rules such as Pinned retain their configured destination.

The preference is enabled by default and can be changed in Settings, where the
four detected standard locations are shown. A custom destination_base outside
Home keeps its explicit root. Organize folder batches keep all moves inside the
selected/reviewed root; they do not silently send a reviewed batch elsewhere.

The implementation reads user-dirs.dirs from XDG_CONFIG_HOME (normally
~/.config), as described by [freedesktop.org](https://wiki.freedesktop.org/www/Software/xdg-user-dirs/).
The file is parsed as data, never sourced as executable shell code. With no valid
entry, conventional Home-based defaults apply. An entry pointing to Home uses
Home directly rather than inventing a disabled standard directory.

Each mapped transfer is validated against its selected desktop root, including
external roots. Symlink escapes below that root are rejected. Changing desktop
folder mappings during processing causes an error that preserves the source.
The existing hash verification, duplicate removal and project protection remain
in effect. Rule Tester shows the actual absolute destination; the proposal's
relative path is relative to that selected destination root.

This affects newly analyzed files. Existing files in older Images/Media/Code/etc.
folders are not bulk-migrated or deleted automatically.
