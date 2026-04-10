const Redis = require('ioredis');

async function testConnection(url) {
  return new Promise((resolve) => {
    const redis = new Redis(url, {
      maxRetriesPerRequest: 0,
      retryStrategy: () => null,
      connectTimeout: 2000
    });
    
    redis.on('connect', () => {
      console.log('SUCCESS:', url);
      redis.disconnect();
      resolve(true);
    });
    
    redis.on('error', (err) => {
      console.log('FAILED:', url, '| ERROR:', err.message);
      redis.disconnect();
      resolve(false);
    });
  });
}

async function run() {
  const p1 = "ipxPRrUJgWKYV82Q0p1kvw5CG2vUS8ljHuEtFpCjQ9fYgbw87vuHXKo1mort7IWo"; // new
  const p2 = "ipxPRrUJgWKYV82Q0p1kvw5CG2vUS8IjHuEtFpCjQ9fYgbw87vuHXKo1mort7lWo"; // old
  
  await testConnection(`redis://default:${p1}@46.225.74.97:6379/0`);
  await testConnection(`redis://:${p1}@46.225.74.97:6379/0`);
  await testConnection(`redis://default:${p2}@46.225.74.97:6379/0`);
  await testConnection(`redis://:${p2}@46.225.74.97:6379/0`);
}
run();
