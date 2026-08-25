const http = require('http');

function post(path, body, token) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const headers = {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(data),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const req = http.request(
      {
        hostname: 'localhost',
        port: 4000,
        path,
        method: 'POST',
        headers,
      },
      (res) => {
        let resp = '';
        res.on('data', (chunk) => (resp += chunk));
        res.on('end', () => resolve({ status: res.statusCode, data: resp }));
      }
    );
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function get(path, token) {
  return new Promise((resolve, reject) => {
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const req = http.request(
      {
        hostname: 'localhost',
        port: 4000,
        path,
        method: 'GET',
        headers,
      },
      (res) => {
        let resp = '';
        res.on('data', (chunk) => (resp += chunk));
        res.on('end', () => resolve({ status: res.statusCode, data: resp }));
      }
    );
    req.on('error', reject);
    req.end();
  });
}

async function run() {
  console.log('Testing login with tom@acme.com...');
  const loginRes = await post('/api/auth/login', { email: 'tom@acme.com', password: 'Datacon123!' });
  console.log('Login status:', loginRes.status);
  const parsed = JSON.parse(loginRes.data);
  console.log('Login user name:', parsed.user?.name, 'Role:', parsed.user?.roleName);
  const token = parsed.token;

  console.log('\nTesting GET /api/insights...');
  const insightsRes = await get('/api/insights', token);
  console.log('Insights status:', insightsRes.status);

  console.log('\nTesting GET /api/connectors...');
  const connectorsRes = await get('/api/connectors', token);
  console.log('Connectors status:', connectorsRes.status);

  console.log('\nTesting GET /api/chat/conversations...');
  const chatRes = await get('/api/chat/conversations', token);
  console.log('Chat conversations status:', chatRes.status);

  console.log('\nTesting GET /api/dashboards...');
  const dashRes = await get('/api/dashboards', token);
  console.log('Dashboards status:', dashRes.status);

  console.log('\nTesting POST /api/chat/stream...');
  const streamRes = await post('/api/chat/stream', { message: 'Why did support tickets spike?' }, token);
  console.log('Chat stream status:', streamRes.status);
  console.log('Chat stream snippet:', streamRes.data.slice(0, 200));
}

run().catch(console.error);

