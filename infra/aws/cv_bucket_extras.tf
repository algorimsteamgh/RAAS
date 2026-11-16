# Lifecycle for the CV bucket (the bucket itself is in data.tf).
# batch/ holds staging copies of batch uploads that the worker deletes after
# processing; anything left behind expires after 7 days. Old versions of CVs
# are kept 90 days. Retention of current CVs follows Quess Global's policy.
resource "aws_s3_bucket_lifecycle_configuration" "cvs" {
  bucket = aws_s3_bucket.cvs.id

  rule {
    id     = "batch-staging"
    status = "Enabled"
    filter {
      prefix = "batch/"
    }
    expiration {
      days = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  rule {
    id     = "noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.cvs]
}
