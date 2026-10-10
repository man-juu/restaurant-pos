/* FR-NTF-005: web push for the installed app. Imported by the generated service worker.
 * The message only says how many notifications are new and where to look; details stay
 * in the app. Text in Indonesian or English, by the device's language. */
const WORDS = {
  id: { title: 'Notifikasi baru', body: (n) => `${n} notifikasi baru. Ketuk untuk membuka.` },
  en: {
    title: 'New notifications',
    body: (n) => `${n} new notification${n === 1 ? '' : 's'}. Tap to open.`,
  },
}

self.addEventListener('push', (event) => {
  let data = { count: 1, link: '/notifications' }
  try {
    data = { ...data, ...event.data.json() }
  } catch {
    /* a push without a readable payload still shows the generic text */
  }
  const lang = (self.navigator.language || 'en').slice(0, 2) === 'id' ? 'id' : 'en'
  const link =
    typeof data.link === 'string' && data.link.startsWith('/') ? data.link : '/notifications'
  event.waitUntil(
    self.registration.showNotification(WORDS[lang].title, {
      body: WORDS[lang].body(Number(data.count) || 1),
      icon: '/icon.svg',
      badge: '/icon.svg',
      tag: 'pos-notifications',
      data: { link },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const link = event.notification.data?.link || '/notifications'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      const open = wins.find((w) => new URL(w.url).origin === self.location.origin)
      if (open) return open.focus().then(() => open.navigate(link))
      return self.clients.openWindow(link)
    }),
  )
})
