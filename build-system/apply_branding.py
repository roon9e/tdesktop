#!/usr/bin/env python3
"""Apply branding to a clean Telegram Desktop checkout.

Reads values from build-system/branding/branding.json and the PEM key from
build-system/branding/server_rsa.pub and rebrands a pristine upstream
Telegram Desktop checkout in place: the tg:// scheme, t.me/telegram.me links,
built-in datacenters and RSA keys, application strings and Windows metadata.

The checkout must be pristine upstream code. Every anchored replacement fails
loudly if its expected text is missing, unless the replacement is already in
place, which makes repeated runs harmless (idempotent).

Run AFTER configure.bat / configure.sh: they regenerate
Telegram/SourceFiles/core/version.h from Telegram/build/version, and the
branded version string would be overwritten otherwise.

Usage:
    python build-system/apply_branding.py
    python build-system/apply_branding.py --root /path/to/tdesktop --dry-run
"""

import argparse
import json
import os
import re
import sys

DEFAULT_APP_NAME = 'Teleram Desktop'
DEFAULT_APP_NAME_SHORT = 'TeleramDesktop'
DEFAULT_PROTOCOL_NAME = 'Teleram Link'
DEFAULT_SCHEME = 'owpg'
DEFAULT_HOST = 'teleram.ru'
DEFAULT_DC_ID = 2
DEFAULT_DC_IP = '31.10.72.76'
DEFAULT_DC_PORT = 45789


class AnchorError(RuntimeError):
    pass


class AlreadyBranded(RuntimeError):
    pass


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_utf8(path):
    with open(path, 'rb') as f:
        raw = f.read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    if bom:
        raw = raw[3:]
    return raw.decode('utf-8'), bom


def write_utf8(path, text, bom):
    raw = text.encode('utf-8')
    if bom:
        raw = b'\xef\xbb\xbf' + raw
    with open(path, 'wb') as f:
        f.write(raw)


def anchored(text, old, new, what):
    count = text.count(old)
    if count == 0:
        if text.count(new) > 0:
            raise AlreadyBranded(what)
        raise AnchorError('anchored text not found in ' + what + ': ' + repr(old))
    if count != 1:
        raise AnchorError('anchored text matched ' + str(count) + ' times in ' + what)
    return text.replace(old, new)


def iter_source_files(root):
    sources = os.path.join(root, 'Telegram', 'SourceFiles')
    for dirpath, dirnames, filenames in os.walk(sources):
        for filename in sorted(filenames):
            if filename.endswith('.cpp') or filename.endswith('.h'):
                yield os.path.join(dirpath, filename)
    langs = os.path.join(root, 'Telegram', 'Resources', 'langs', 'lang.strings')
    if os.path.isfile(langs):
        yield langs


def make_dc_options_block(dc_id, dc_ip, dc_port, rsa_lines, eol):
    dcentry = '\t{%d, "%s", %d}' % (dc_id, dc_ip, dc_port)
    empty = '\t{ 0, "", 0 }'

    def dc_array(name, entry):
        return ['const BuiltInDc %s[] = {' % name, entry, '};']

    def rsa_array(name, lines):
        result = ['const char *%s[] = { "\\' % name]
        for index, line in enumerate(lines):
            suffix = '\\n\\' if index + 1 < len(lines) else '" };'
            result.append(line + suffix)
        return result

    lines = []
    lines += dc_array('kBuiltInDcs', dcentry)
    lines += ['']
    lines += dc_array('kBuiltInDcsIPv6', empty)
    lines += ['']
    lines += dc_array('kBuiltInDcsTest', dcentry)
    lines += ['']
    lines += dc_array('kBuiltInDcsIPv6Test', empty)
    lines += ['']
    lines += rsa_array('kTestPublicRSAKeys', rsa_lines)
    lines += ['']
    lines += rsa_array('kPublicRSAKeys', rsa_lines)
    return eol.join(lines)


def transform_dc_options(text, dc_id, dc_ip, dc_port, rsa_lines):
    start_marker = 'const BuiltInDc kBuiltInDcs[] = {'
    end_marker = '-----END RSA PUBLIC KEY-----" };'
    start_index = text.find(start_marker)
    end_index = text.find(end_marker)
    if start_index < 0 or end_index < 0:
        raise AnchorError('mtproto_dc_options.cpp block markers not found')
    start = text.rfind('\n', 0, start_index) + 1
    end = text.find('\n', end_index + len(end_marker))
    eol = '\r\n' if '\r\n' in text else '\n'
    block = make_dc_options_block(dc_id, dc_ip, dc_port, rsa_lines, eol)
    return text[:start] + block + text[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--root',
        help='repository root (default: parent of build-system/)')
    parser.add_argument('--branding', help='path to branding.json')
    parser.add_argument('--rsa', help='path to server_rsa.pub')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='report what would change without writing files')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    root = os.path.abspath(args.root) if args.root else repo_root()
    default_dir = os.path.join(root, 'build-system', 'branding')
    branding_path = os.path.abspath(args.branding) if args.branding else os.path.join(default_dir, 'branding.json')
    rsa_path = os.path.abspath(args.rsa) if args.rsa else os.path.join(default_dir, 'server_rsa.pub')

    with open(branding_path, encoding='utf-8') as f:
        config = json.load(f)
    general = config.get('general', {})
    datacenter = config.get('datacenter', {})

    app_name = general.get('app_name', DEFAULT_APP_NAME)
    app_name_short = general.get('app_name_short', DEFAULT_APP_NAME_SHORT)
    protocol_name = general.get('protocol_name', DEFAULT_PROTOCOL_NAME)
    scheme = general.get('url_scheme', DEFAULT_SCHEME)
    host = general.get('host', DEFAULT_HOST)
    company_name = general.get('company_name')
    dc_id = int(datacenter.get('id', DEFAULT_DC_ID))
    dc_ip = datacenter.get('ip', DEFAULT_DC_IP)
    dc_port = int(datacenter.get('port', DEFAULT_DC_PORT))

    if not re.fullmatch(r'[A-Za-z0-9]+', scheme):
        sys.exit('url_scheme must be alphanumeric: ' + repr(scheme))
    if not host or '/' in host or '.' not in host:
        sys.exit('host must be a bare domain name: ' + repr(host))
    if not app_name_short:
        sys.exit('app_name_short must not be empty (used by QApplication::setApplicationName)')

    with open(rsa_path, encoding='utf-8-sig') as f:
        rsa_text = f.read()
    rsa_lines = [line.strip() for line in rsa_text.replace('\r\n', '\n').split('\n') if line.strip()]
    if (len(rsa_lines) < 3
            or rsa_lines[0] != '-----BEGIN RSA PUBLIC KEY-----'
            or rsa_lines[-1] != '-----END RSA PUBLIC KEY-----'):
        sys.exit('server_rsa.pub must be a PEM-encoded PKCS#1 RSA public key')

    raw_host = re.escape(host)
    cpp_host = host.replace('.', r'\\.')

    changed = []
    errors = []
    state = {}

    def note(relpath):
        if relpath not in changed:
            changed.append(relpath)

    def load(relpath):
        key = relpath.replace('/', os.sep)
        if key not in state:
            state[key] = read_utf8(os.path.join(root, key))
        return state[key]

    def commit(relpath, new_text):
        key = relpath.replace('/', os.sep)
        old_text, bom = state[key]
        if new_text == old_text:
            return
        state[key] = (new_text, bom)
        if not args.dry_run:
            write_utf8(os.path.join(root, key), new_text, bom)
        note(relpath)

    for path in iter_source_files(root):
        if not os.path.isfile(path):
            continue
        text, bom = read_utf8(path)
        result = text.replace('tg://', scheme + '://')
        result = re.sub(r'(?<![A-Za-z0-9_])t\.me(?![A-Za-z0-9_])', host, result)
        result = re.sub(r'(?<![A-Za-z0-9_])telegram\.me(?![A-Za-z0-9_])', host, result)
        result = re.sub(r'(?<![A-Za-z0-9_])telegram\.dog(?![A-Za-z0-9_])', host, result)
        if result != text:
            state[os.path.relpath(path, root)] = (result, bom)
            if not args.dry_run:
                write_utf8(path, result, bom)
            note(os.path.relpath(path, root).replace('\\', '/'))

    transforms = []

    def transform(relpath):
        def decorate(fn):
            transforms.append((relpath, fn))
            return fn
        return decorate

    @transform('Telegram/SourceFiles/core/version.h')
    def version_header(text):
        return anchored(
            text,
            'constexpr auto AppName = "Telegram Desktop"_cs;',
            'constexpr auto AppName = "%s"_cs;' % app_name,
            'version.h AppName')

    @transform('Telegram/SourceFiles/core/launcher.cpp')
    def launcher(text):
        return anchored(
            text,
            '\tQApplication::setApplicationName(u"TelegramDesktop"_q);',
            '\tQApplication::setApplicationName(u"%s"_q);' % app_name_short,
            'launcher.cpp setApplicationName')

    @transform('Telegram/SourceFiles/core/application.cpp')
    def application(text):
        text = anchored(
            text,
            '\t\t.protocol = u"tg"_q,',
            '\t\t.protocol = u"%s"_q,' % scheme,
            'application.cpp protocol')
        return anchored(
            text,
            '\t\t.protocolName = u"Telegram Link"_q,',
            '\t\t.protocolName = u"%s"_q,' % protocol_name,
            'application.cpp protocolName')

    @transform('Telegram/SourceFiles/mtproto/mtproto_config.h')
    def mtproto_config_h(text):
        return anchored(
            text,
            '\tQString internalLinksDomain = u"https://t.me/"_q;',
            '\tQString internalLinksDomain = u"https://%s/"_q;' % host,
            'mtproto_config.h internalLinksDomain')

    @transform('Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp')
    def mtproto_dc_options(text):
        return transform_dc_options(text, dc_id, dc_ip, dc_port, rsa_lines)

    @transform('Telegram/SourceFiles/core/local_url_handlers.cpp')
    def local_url_handlers(text):
        text = anchored(
            text,
            '\tauto subdomainMatch = regex_match(u"^(https?://)?([a-zA-Z0-9\\\\_]+)\\\\.t\\\\.me(/\\\\d+)?/?(\\\\?.+)?"_q, url, matchOptions);',
            '\tauto subdomainMatch = regex_match(u"^(https?://)?([a-zA-Z0-9\\\\_]+)\\\\.%s(/\\\\d+)?/?(\\\\?.+)?"_q, url, matchOptions);' % cpp_host,
            'local_url_handlers.cpp subdomainMatch')
        text = anchored(
            text,
            '\tauto telegramMeMatch = regex_match(u"^(https?://)?(www\\\\.)?(telegram\\\\.(me|dog)|t\\\\.me)/(.+)$"_q, url, matchOptions);',
            '\tauto telegramMeMatch = regex_match(u"^(https?://)?(www\\\\.)?%s/(.+)$"_q, url, matchOptions);' % cpp_host,
            'local_url_handlers.cpp telegramMeMatch')
        return anchored(
            text,
            '\t\tconst auto query = telegramMeMatch->capturedView(5);',
            '\t\tconst auto query = telegramMeMatch->capturedView(3);',
            'local_url_handlers.cpp capturedView')

    @transform('Telegram/SourceFiles/boxes/connection_box.cpp')
    def connection_box(text):
        return anchored(
            text,
            '\t\tR"((?:https?:\/\/[^\s]+|tg:\/\/[^\s]+|(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)\/[^\s]+))",',
            '\t\tR"((?:https?:\/\/[^\s]+|%s:\/\/[^\s]+|(?:www\.)?%s\/[^\s]+))",' % (scheme, raw_host),
            'connection_box.cpp urlRegex')

    @transform('Telegram/SourceFiles/core/click_handler_types.cpp')
    def click_handler_types(text):
        text = anchored(
            text,
            '\t\t"(^|\\\\.)(telegram\\\\.(me|dog)|t\\\\.me)$",',
            '\t\t"(^|\\\\.)%s$",' % cpp_host,
            'click_handler_types.cpp short link host')
        text = anchored(
            text,
            '\t\t"telegram\\\\.(org|me|dog)"',
            '\t\t"telegram\\\\.org"',
            'click_handler_types.cpp trusted host list')
        return anchored(
            text,
            '\t\t"|t\\\\.me"',
            '\t\t"|%s"' % cpp_host,
            'click_handler_types.cpp trusted host fallback')

    @transform('Telegram/SourceFiles/main/main_session.cpp')
    def main_session(text):
        return anchored(
            text,
            "\t// Like 'https://%s/' or 'https://%s/'." % (host, host),
            "\t// Like 'https://%s/'." % host,
            'main_session.cpp link comment')

    @transform('Telegram/SourceFiles/boxes/choose_filter_box.cpp')
    def choose_filter_box(text):
        return anchored(
            text,
            '\t\t\ttext = text.mid(13);',
            '\t\t\ttext = text.mid(%d);' % len('https://%s/' % host),
            'choose_filter_box.cpp mid')

    @transform('Telegram/lib_base/base/qthelp_url.cpp')
    def lib_base_protocol(text):
        return anchored(
            text,
            '|| equals(qstr("tg"))',
            '|| equals(qstr("%s"))' % scheme,
            'lib_base qthelp_url protocol')

    @transform('Telegram/lib_ui/ui/text/text_entity.cpp')
    def lib_ui_protocol(text):
        return anchored(
            text,
            'addOne(QString::fromLatin1("tg")); // local urls',
            'addOne(QString::fromLatin1("%s")); // local urls' % scheme,
            'lib_ui text_entity protocol')

    @transform('Telegram/Resources/winrc/Telegram.rc')
    def telegram_rc(text):
        text = anchored(
            text,
            'VALUE "FileDescription", "Telegram Desktop"',
            'VALUE "FileDescription", "%s"' % app_name,
            'Telegram.rc FileDescription')
        return anchored(
            text,
            'VALUE "ProductName", "Telegram Desktop"',
            'VALUE "ProductName", "%s"' % app_name,
            'Telegram.rc ProductName')

    @transform('Telegram/Resources/winrc/Updater.rc')
    def updater_rc(text):
        text = anchored(
            text,
            'VALUE "FileDescription", "Telegram Desktop Updater"',
            'VALUE "FileDescription", "%s Updater"' % app_name,
            'Updater.rc FileDescription')
        return anchored(
            text,
            'VALUE "ProductName", "Telegram Desktop"',
            'VALUE "ProductName", "%s"' % app_name,
            'Updater.rc ProductName')

    rc_company = (
        ('VALUE "CompanyName", "Telegram FZ-LLC"',
         'VALUE "CompanyName", "%s"' % company_name)
        if company_name else None)

    @transform('Telegram/Resources/winrc/Telegram.rc')
    def telegram_rc_company(text):
        if rc_company is None:
            return text
        return anchored(text, rc_company[0], rc_company[1], 'Telegram.rc CompanyName')

    @transform('Telegram/Resources/winrc/Updater.rc')
    def updater_rc_company(text):
        if rc_company is None:
            return text
        return anchored(text, rc_company[0], rc_company[1], 'Updater.rc CompanyName')

    for relpath, fn in transforms:
        if not os.path.isfile(os.path.join(root, relpath.replace('/', os.sep))):
            errors.append('missing file: ' + relpath)
            continue
        try:
            text, bom = load(relpath)
            commit(relpath, fn(text))
        except AlreadyBranded as e:
            if args.verbose:
                print('skip (already branded): ' + str(e))
        except (AnchorError, RuntimeError) as e:
            errors.append(str(e))

    if changed:
        print('changed %d file(s):' % len(changed))
        for rel in changed:
            print('  ' + rel)
    else:
        print('no changes to make' if not errors else 'no changes applied')

    if errors:
        print('errors:', file=sys.stderr)
        for error in errors:
            print('  ' + error, file=sys.stderr)
        sys.exit(1)

    print('done: %s / %s / %s' % (app_name, scheme, host))


if __name__ == '__main__':
    main()