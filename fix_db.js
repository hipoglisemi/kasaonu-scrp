const { Client } = require('pg');
const client = new Client({ connectionString: 'postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres' });
client.connect().then(async () => {
  await client.query(`ALTER TABLE "test_campaigns" ADD COLUMN IF NOT EXISTS "cards_audited_at" TIMESTAMP;`);
  console.log("Added cards_audited_at to test_campaigns");
  client.end();
}).catch(e => console.error(e));
