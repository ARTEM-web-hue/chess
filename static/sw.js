self.addEventListener('push', (event) => {
  let data = { title: 'Новое сообщение', body: 'В чате новое сообщение!' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || 'Новое сообщение в чате',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [100, 50, 100],
     { url: '/' }
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Анонимный чат', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      const url = event.notification.data?.url || '/';
      for (let i = 0; i < clientList.length; i++) {
        let client = clientList[i];
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

self.addEventListener('fetch', () => {});
