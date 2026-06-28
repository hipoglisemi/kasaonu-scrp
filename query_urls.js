const { PrismaClient } = require('@prisma/client')
const prisma = new PrismaClient()
async function main() {
  const campaigns = await prisma.campaign.findMany({
    where: { id: { in: [14921, 15973, 10484] } },
    select: { id: true, original_url: true, title: true }
  })
  console.log(campaigns)
}
main().catch(console.error).finally(() => prisma.$disconnect())
