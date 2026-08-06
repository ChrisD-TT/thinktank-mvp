import cors from 'cors'
import express from 'express'
import { Storage } from '@google-cloud/storage'

const app = express()
const port = Number(process.env.PORT || 8080)
const bucketName = process.env.GCS_BUCKET_NAME || 'abyassatlas'
const objectPath = process.env.GCS_ATLAS_OBJECT || 'curated/atlas.json'
const allowedOrigin = process.env.ALLOWED_ORIGIN || '*'

const storage = new Storage()
const bucket = storage.bucket(bucketName)
const atlasFile = bucket.file(objectPath)

app.use(
  cors({
    origin: allowedOrigin,
  }),
)

app.get('/health', (_req, res) => {
  res.json({ ok: true, bucketName, objectPath })
})

app.get('/api/atlas', async (_req, res) => {
  try {
    const [exists] = await atlasFile.exists()

    if (!exists) {
      res.status(404).json({
        error: 'Atlas object not found',
        bucketName,
        objectPath,
      })
      return
    }

    const [contents] = await atlasFile.download()
    const payload = JSON.parse(contents.toString('utf8'))

    res.setHeader('Cache-Control', 'public, max-age=60')
    res.json(payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown proxy error'

    res.status(500).json({
      error: 'Failed to load atlas data from Google Cloud Storage',
      details: message,
      bucketName,
      objectPath,
    })
  }
})

app.listen(port, () => {
  console.log(
    JSON.stringify({
      message: 'Ocean Atlas proxy listening',
      port,
      bucketName,
      objectPath,
      allowedOrigin,
    }),
  )
})
