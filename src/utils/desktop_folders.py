"""Resolve Home-based download routes through Linux desktop user directories."""
from dataclasses import replace
import os
from pathlib import Path
import shlex

from src.core.file_intelligence.context import EvidenceItem, SignalType

_DEFAULTS = {'PICTURES':'Pictures','VIDEOS':'Videos','MUSIC':'Music','DOCUMENTS':'Documents','DOWNLOAD':'Downloads'}
_ALIASES = {'Images':'PICTURES','Pictures':'PICTURES','Videos':'VIDEOS','Audio':'MUSIC','Music':'MUSIC','Documents':'DOCUMENTS'}
_DOCUMENT_DOMAINS = {'College','Work','Projects','Code','Cybersecurity'}
_DOWNLOAD_DOMAINS = {'Archives','Applications','Others','Media'}
_FORBIDDEN = ('/etc','/usr','/bin','/sbin','/lib','/lib64','/proc','/sys','/dev','/boot','/run')


def desktop_folders():
    """Read user-dirs.dirs as data, without sourcing or executing shell text."""
    home = os.path.abspath(str(Path.home()))
    result = {key:os.path.join(home,name) for key,name in _DEFAULTS.items()}
    configured = os.environ.get('XDG_CONFIG_HOME','')
    config = Path(configured) if configured and os.path.isabs(configured) else Path(home)/'.config'
    try:
        with (config/'user-dirs.dirs').open(encoding='utf-8') as handle:
            text = handle.read(65536)
    except (OSError,UnicodeError):
        text = ''
    for line in text.splitlines():
        try:
            tokens = shlex.split(line,comments=True,posix=True)
        except ValueError:
            continue
        if len(tokens)!=1 or '=' not in tokens[0]:
            continue
        key,value = tokens[0].split('=',1)
        if not key.startswith('XDG_') or not key.endswith('_DIR'):
            continue
        category = key[4:-4]
        if category not in result:
            continue
        if value=='$HOME' or value.startswith('$HOME/'):
            value=home+value[5:]
        if (not os.path.isabs(value) or '$' in value or '`' in value or
                any(ord(char)<32 or ord(char)==127 for char in value)):
            continue
        value=os.path.realpath(value)
        if value=='/' or any(value==prefix or value.startswith(prefix+'/') for prefix in _FORBIDDEN):
            continue
        result[category]=value
    return {key:os.path.realpath(value) for key,value in result.items()}


class DesktopDestinations:
    def __init__(self,base,config):
        self.base=os.path.realpath(base)
        self.active=bool(config.get('use_desktop_folders',True) and self.base==os.path.realpath(str(Path.home())))
        self.selected_root=self.base
        self.folders=desktop_folders() if self.active else {}
        self.signature=(self.active,tuple(sorted(self.folders.items())))

    def route(self,relative,*,is_rule=False):
        """Return an explicitly approved root and a path beneath that root."""
        parts=relative.split(os.sep)
        if not self.active or len(parts)<2:
            return self.base,relative,None
        category=parts[0];key=_ALIASES.get(category);remaining=parts[1:]
        if category=='Media' and len(parts)>2 and parts[1] in _ALIASES:
            key=_ALIASES[parts[1]];remaining=parts[2:]
        elif key is None and not is_rule:
            if category in _DOCUMENT_DOMAINS:
                key='DOCUMENTS';remaining=parts
            elif category in _DOWNLOAD_DOMAINS:
                key='DOWNLOAD';remaining=parts
        if key is None:
            return self.base,relative,None
        return self.folders[key],os.path.join(*remaining),key

    def apply(self,proposal,planner):
        root,relative,key=self.route(proposal.relative_target,is_rule=proposal.is_rule_override)
        root,target=planner._validate_boundary(root,os.path.join(root,relative))
        self.selected_root=root
        evidence=list(proposal.evidence)
        if key is not None:
            evidence.append(EvidenceItem(SignalType.DIRECTORY_CONTEXT,
                f'Using Linux desktop {key.title()} folder',0.0,'desktop.directories'))
        return replace(proposal,target_path=target,relative_target=relative,
                       hierarchy_segments=relative.split(os.sep)[:-1],evidence=evidence),root
