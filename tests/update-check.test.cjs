const {test}=require('node:test');
const assert=require('node:assert/strict');
require('../extension/update-check.js');
const upd=globalThis.namaDLUpdate;

test('parseVersion accepts plain and v-prefixed versions',()=>{
 assert.deepEqual(upd.parseVersion('1.15.0'),[1,15,0]);
 assert.deepEqual(upd.parseVersion('v1.15.0'),[1,15,0]);
 assert.equal(upd.parseVersion('1.15'),null);
 assert.equal(upd.parseVersion('latest'),null);
 assert.equal(upd.parseVersion(''),null);
});

test('isNewer compares numerically, not as strings',()=>{
 assert.equal(upd.isNewer('v1.15.0','1.14.0'),true);
 assert.equal(upd.isNewer('v1.14.0','1.14.0'),false);
 assert.equal(upd.isNewer('v1.13.9','1.14.0'),false);
 assert.equal(upd.isNewer('v1.14.1','1.14.0'),true);
 assert.equal(upd.isNewer('v2.0.0','1.99.99'),true);
 assert.equal(upd.isNewer('garbage','1.14.0'),false);
});

test('notice returns version and URL only for a newer published release',()=>{
 const rel={tag_name:'v1.15.0',html_url:'https://github.com/kokenamazu-boop/nama_DL/releases/tag/v1.15.0',draft:false,prerelease:false};
 assert.deepEqual(upd.notice(rel,'1.14.0'),{version:'1.15.0',url:rel.html_url});
 assert.equal(upd.notice(rel,'1.15.0'),null);
 assert.equal(upd.notice({...rel,draft:true},'1.14.0'),null);
 assert.equal(upd.notice({...rel,prerelease:true},'1.14.0'),null);
 assert.equal(upd.notice(null,'1.14.0'),null);
 assert.equal(upd.notice({},'1.14.0'),null);
});

test('notice falls back to the releases page for a non-GitHub URL',()=>{
 const rel={tag_name:'v9.9.9',html_url:'https://example.com/x',draft:false,prerelease:false};
 assert.equal(upd.notice(rel,'1.14.0').url,upd.RELEASES_PAGE);
});
