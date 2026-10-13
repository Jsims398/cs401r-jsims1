## ADR-001: NorthStar Platform Foundation

### Status
Accepted

### Context
NorthStar Retail is standing up one AWS platform to carry three separate AI systems: a churn prediction model, an offer-generation model, and an LLM-based customer service agent. All are sharing the same S3 data and the same SageMaker environment. That sharing is exactly what makes the need for the identity model and
storage-tier structure.

Without an identity model, the credentials used to train the churn model are also the credentials that can read and overwrite the raw customer data feeding the offer-generation pipeline and the conversation logs the service agent learns from. 

Without a storage-tier structure, there is noway to tell, by looking at a bucket, whether an object is raw ingested data that has never been validated, or a scored model artifact safe to serve predictions from.

Lab 1 implemented that structure so nothing is overwritten or lost. 

### Decision
**Network.** One VPC, `northstar-dev-vpc` (`10.0.0.0/16`), with a singlepublic subnet, `northstar-dev-public-1` (`10.0.100.0/24`) in `us-east-1a`. An Internet Gateway (`northstar-dev-igw`) and route table (`northstar-dev-public-rt`, `0.0.0.0/0 -> igw`) give SageMaker Studio the internet path it needs to pull container images and serve its UI. A single security group (`northstar-dev-sagemaker-sg`) restricts inbound traffic to the VPC CIDR only (`10.0.0.0/16`) so nothing on the internet reaches Studio
directly, even though Studio can reach out. This will support the three system platform that will be developed. 

**Storage.** One S3 bucket, `northstar-dev-data-{account-id}`, with four logical folders: `raw/`, `processed/`, `features/`, `artifacts/`. A single bucket for simplicity and cost optimization. Versioning and SSE-S3 encryption are both enabled, because models are exactly the kind of artifact you want to roll back after a bad training run overwrites a working one.

**Identity.** `northstar-dev-MLEngineer`, trusted only by `sagemaker.amazonaws.com`. Its inline policy is split by concern rather than one blanket S3 statement which has access to /artifacts/*` and `.../features/*` only. This is to protect the true raw and processed data. 

**ML development environment.** SageMaker Studio, via one Domain (`northstar-dev-domain`) and one user profile (`MLEngineer`), placed in the public subnet for Lab 1 and pointed at the MLEngineer role as its execution role. This is to allow the Engineers to be able to develope and train models and evaluation for churn scoring. 

### Consequences
#### What this makes easy
By developing the terraform design we are now able to version control the entire AWS design which we currently have. This allows for tracked chagnes and simplicity when adding new features. The actual AWS design is simple and structural this allows for early developement work to begin so that the company can work efficently on proving these AI models are good. It also makes data easy to locate because it is all within one S3 bucket.

#### What this makes harder
Cost and usage attribution across the three AI systems is harder with one shared bucket than separate buckets, since S3 cost and access logs are per-bucket. This will be harder to track and manage what is happening when an entire team is working with the data and it is all in one shared location. 

#### What would cause you to revisit this decision
If a second team needed to operate on this data under a materially different rules or reasons. Say the service agent's conversation logs became subject to a retention requirement or legal issue. A second bucket or S3 Access Points becomes the next step for expansion and data protection. 

### Alternative Considered
A bucket-per-stage layout (`northstar-dev-raw`, `northstar-dev-processed`, `northstar-dev-features`, `northstar-dev-artifacts`) was considered instead of one bucket with four prefixes. It would make IAM permissions set at the bucket-level instead of ARN-pattern-based which helps with set security rules and practices. It was rejected because four buckets mean four sets of encryption, versioning, and public-access-block settings to keep in sync as the platform grows. 

### AWS Service Selection
- **Networking isolation model:** a single VPC with one public subnet and a VPC-CIDR-only security group, because the only network consumer is SageMaker Studio, which needs outbound internet access but no inbound exposure.
- **Storage design:** one versioned, SSE-S3-encrypted S3 bucket with raw/processed/features/artifacts folders, because the three NorthStar systems share a data pipeline and for ease of cost and security. 
- **Identity model:** a single least-privilege IAM role trusted only by `sagemaker.amazonaws.com`, with S3 access split into object-level and bucket-level statements, because the role that trains and registers models must never be able to write to unvalidated ingested data.
- **ML development environment:** SageMaker Studio via a Domain and user profile, it runs directly under the MLEngineer execution role, making the IAM boundary visible the moment a notebook opens.
