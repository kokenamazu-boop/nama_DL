// Shared X URL rules for page buttons, the popup and the service worker.
globalThis.namaDLSites = {
 isXHost(host) { return ['x.com','www.x.com','twitter.com','www.twitter.com'].includes(host); },
 xPostURL(value,base) {
  try {
   const u=new URL(value,base);
   if(u.protocol!=='https:'||u.username||u.password||u.port||!this.isXHost(u.hostname))return null;
   const post=u.pathname.match(/^\/(?:(i\/web|[A-Za-z0-9_]+)\/status|statuses)\/(\d+)(?:\/(?:video|photo)\/[1-9]\d*)?\/?$/);
   return post?'https://x.com/'+(post[1]||'i/web')+'/status/'+post[2]:null;
  } catch { return null; }
 },
 authKey(value) {
  const u=new URL(value);
  return this.isXHost(u.hostname)?'https://x.com':u.origin;
 }
};
