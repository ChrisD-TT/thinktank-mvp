param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [Parameter(Mandatory = $true)]
  [string]$BucketName,

  [string]$Region = 'us-central1',
  [switch]$EnableVersioning
)

$ErrorActionPreference = 'Stop'

Write-Host "Setting active project to $ProjectId"
gcloud config set project $ProjectId | Out-Null

Write-Host "Checking whether bucket gs://$BucketName already exists"
$bucketExists = $false
try {
  gcloud storage buckets describe "gs://$BucketName" | Out-Null
  $bucketExists = $true
} catch {
  $bucketExists = $false
}

if ($bucketExists) {
  Write-Host "Bucket gs://$BucketName already exists. No changes made."
  exit 0
}

Write-Host "Creating bucket gs://$BucketName in $Region"
gcloud storage buckets create "gs://$BucketName" --location=$Region --uniform-bucket-level-access

if ($EnableVersioning) {
  Write-Host "Enabling object versioning"
  gcloud storage buckets update "gs://$BucketName" --versioning
}

Write-Host "Bucket ready: gs://$BucketName"
Write-Host "Suggested next steps:"
Write-Host "  1. Add raw ocean source files under a raw/ prefix"
Write-Host "  2. Add processed atlas exports under a curated/ prefix"
Write-Host "  3. Add generated meshes or tiles under a models/ prefix"
