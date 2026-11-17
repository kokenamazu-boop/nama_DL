// New-version check against this project's GitHub Releases.
// The comparison logic is pure and tested; the popup does the fetch
// (at most once a day) and only ever reads the public release info.
globalThis.namaDLUpdate = {
API: 'https://api.github.com/repos/kokenamazu-boop/nama_DL/releases/latest',
RELEASES_PAGE: 'https://github.com/kokenamazu-boop/nama_DL/releases',
parseVersion(text) {
const m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(String(text ?? '').trim());
return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
},
isNewer(latest, current) {
const a = this.parseVersion(latest), b = this.parseVersion(current);
if (!a || !b) return false;
for (let i = 0; i < 3; i++) { if (a[i] !== b[i]) return a[i] > b[i]; }
return false;
},
notice(release, currentVersion) {
if (!release || typeof release !== 'object') return null;
if (release.draft || release.prerelease) return null;
const tag = String(release.tag_name ?? '');
if (!this.isNewer(tag, currentVersion)) return null;
const url = /^https:\/\/github\.com\//.test(String(release.html_url ?? ''))
  ? String(release.html_url) : this.RELEASES_PAGE;
return {version: tag.replace(/^v/, ''), url};
},
};
