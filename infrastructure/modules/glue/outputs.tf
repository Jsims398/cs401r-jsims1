output "database_name" {
  description = "Glue Data Catalog database name"
  value       = aws_glue_catalog_database.this.name
}

output "crawler_name" {
  description = "Name of the raw-data crawler"
  value       = aws_glue_crawler.raw.name
}

output "transform_job_name" {
  description = "Name of the raw -> processed transform job"
  value       = aws_glue_job.transform.name
}

output "feature_engineer_job_name" {
  description = "Name of the processed -> features feature-engineer job"
  value       = aws_glue_job.feature_engineer.name
}
