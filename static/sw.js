self.addEventListener('push', function(event) {
    console.log('Push event received:', event);
    
    if (!event.data) {
        console.log('No data in push event');
        return;
    }
    
    try {
        const data = event.data.json();
        console.log('Push data:', data);
        
        const options = {
            body: data.body,
            icon: '/icon-192.png',
            badge: '/icon-192.png',
            vibrate: [100, 50, 100],
            data: {
                url: '/'
            },
            actions: [
                {
                    action: 'open',
                    title: 'Открыть чат'
                }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    } catch (error) {
        console.error('Error processing push:', error);
    }
});

self.addEventListener('notificationclick', function(event) {
    console.log('Notification clicked');
    event.notification.close();
    
    event.waitUntil(
        clients.matchAll({type: 'window', includeUncontrolled: true}).then(windowClients => {
            // Проверяем, есть ли уже открытое окно
            for (let client of windowClients) {
                if (client.url.includes(location.origin) && 'focus' in client) {
                    return client.focus();
                }
            }
            // Если нет открытого окна - открываем новое
            if (clients.openWindow) {
                return clients.openWindow('/');
            }
        })
    );
});

// Важно: добавить активацию Service Worker
self.addEventListener('activate', function(event) {
    console.log('Service Worker activated');
    event.waitUntil(self.clients.claim());
});
