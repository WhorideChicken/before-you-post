// Takes photos shared from another app (Android share sheet, after installing the app) and keeps them on the device:
// nothing is uploaded until you tap Check on the page. Every other request goes to the network as usual.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "POST" || new URL(e.request.url).pathname !== "/share") return;
  e.respondWith((async () => {
    const files = (await e.request.formData()).getAll("photos").filter(f => f instanceof File);
    await caches.delete("shared");
    const cache = await caches.open("shared");
    await Promise.all(files.map((f, i) => cache.put(`/shared/${i}`,
      new Response(f, { headers: { "content-type": f.type, "x-name": encodeURIComponent(f.name) } }))));
    return Response.redirect(`/?shared=${files.length}#own`, 303);
  })());
});
