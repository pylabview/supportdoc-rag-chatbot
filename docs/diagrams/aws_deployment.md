# AWS Deployment Diagram

Canonical AWS deployment diagram for the SupportDoc RAG Chatbot baseline described in `docs/architecture/aws_deployment.md`.

Source of truth: `docs/diagrams/aws_deployment.mmd`

```mermaid
flowchart TB
    User[User or future React SPA] --> ALB[Application Load Balancer]
    ALB --> API[ECS Fargate service\nFastAPI backend]
    API --> RDS[(RDS PostgreSQL\npgvector)]
    API --> INF[EC2 GPU inference host\nvLLM or TGI]
    API --> CW[CloudWatch Logs / Metrics]
    API --> CFG[Secrets Manager /\nSSM Parameter Store]

    subgraph Artifact Plane
        S3[(S3 corpus + artifacts)]
        ING[Ingestion / promotion job]
        S3 --> ING
        ING --> RDS
        ING --> S3
    end

    SPA[Future React SPA\nAmplify Hosting] -. future public client .-> ALB
```
