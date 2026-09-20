const http = require('http');
const options = {hostname: '127.0.0.1', port: 9224, path: '/json/list', method: 'GET'};
const req = http.request(options, (res) => {
    let data = '';
    res.on('data', (chunk) => data += chunk);
    res.on('end', () => {
        try {
            const parsed = JSON.parse(data);
            console.log('Targets:', parsed.length);
            console.log('First:', parsed[0]?.url || 'none');
        } catch(e) {
            console.log('Raw:', data.substring(0, 200));
        }
    });
});
req.on('error', (e) => console.error('Error:', e.message));
req.end();
