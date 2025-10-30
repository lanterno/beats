# Terraform Deployment to Render.com

This directory contains Terraform configuration to deploy the Beats FastAPI application to Render.com.

## Prerequisites

1. **Render Account**: Sign up at [render.com](https://render.com)
2. **Render API Key**: Generate from [dashboard.render.com/account/api-keys](https://dashboard.render.com/account/api-keys)
3. **Render Owner ID**: Find in [dashboard.render.com/settings](https://dashboard.render.com/settings) under "Account ID" (starts with `usr-`) or "Team ID" (starts with `tea-`)
4. **MongoDB Atlas** (or other MongoDB provider): Get connection string
5. **Terraform**: Install from [terraform.io/downloads](https://terraform.io/downloads)
6. **GitHub Repository**: Your code should be pushed to GitHub

## Quick Start

### 1. Configure Variables

Copy the example variables file and fill in your values:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:
- `render_api_key`: Your Render API key from [dashboard.render.com/account/api-keys](https://dashboard.render.com/account/api-keys)
- `render_owner_id`: Your account ID from [dashboard.render.com/settings](https://dashboard.render.com/settings) (starts with `usr-` or `tea-`)
- `db_dsn`: MongoDB connection string (e.g., from MongoDB Atlas)
- `access_token`: Generate a secure random token for API authentication

**⚠️ IMPORTANT**: Never commit `terraform.tfvars` to version control!

### 2. Initialize Terraform

```bash
terraform init
```

This downloads the Render provider plugin.

### 3. Review the Plan

```bash
terraform plan
```

Review the resources that will be created.

### 4. Deploy

```bash
terraform apply
```

Type `yes` when prompted to confirm deployment.

### 5. Get Service URL

After deployment completes, Terraform will output your service URL:

```bash
terraform output service_url
```

## Configuration

### Service Plans

Available Render plans (set in `service_plan` variable):
- `free`: 750 hours/month, sleeps after 15 min inactivity
- `starter`: $7/month, always on
- `standard`: $25/month, higher resources
- `pro`: Custom pricing

### Regions

Available regions (set in `region` variable):
- `oregon` (US West)
- `frankfurt` (EU)
- `singapore` (Asia)
- `ohio` (US East)
- `virginia` (US East)

### Environment Variables

The following environment variables are automatically configured:
- `PORT`: Set to 10000 (Render default)
- `DB_DSN`: MongoDB connection string
- `DB_NAME`: Database name
- `ACCESS_TOKEN`: API authentication token

## MongoDB Setup

### Using MongoDB Atlas (Recommended)

1. Create account at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Create a free cluster
3. Create a database user
4. Add `0.0.0.0/0` to IP whitelist (for Render access)
5. Get connection string (format: `mongodb+srv://...`)
6. Use this as `db_dsn` in `terraform.tfvars`

## Managing the Deployment

### View Service Status

```bash
terraform show
```

### Update Configuration

1. Edit variables in `terraform.tfvars`
2. Run `terraform plan` to review changes
3. Run `terraform apply` to apply changes

### Destroy Service

```bash
terraform destroy
```

## Troubleshooting

### Check Service Logs

Visit: https://dashboard.render.com/web/{service_id}

Or use Terraform output:
```bash
terraform output deploy_url
```

### Health Check

Your service health check endpoint is `/talk/ding`

Test after deployment:
```bash
curl https://your-service.onrender.com/talk/ding
```

Should return: `{"message": "dong"}`

### Service Not Starting

1. Check logs in Render dashboard
2. Verify Docker build succeeds locally: `make test`
3. Verify environment variables are set correctly
4. Ensure MongoDB connection string is correct and accessible

## CI/CD

By default, `auto_deploy = true` means Render will automatically deploy when you push to the configured branch (`main`).

To disable auto-deploy:
```hcl
auto_deploy = false
```

## Cost Estimation

- **Free Plan**: $0/month (sleeps after 15 min inactivity)
- **MongoDB Atlas Free**: $0/month (512 MB storage)

**Total minimum cost**: $0/month

For production, consider:
- **Starter Plan**: $7/month (always on)
- **MongoDB Atlas M10**: ~$57/month (dedicated cluster)

## Security Notes

1. Never commit `terraform.tfvars` or any file with credentials
2. Use strong, random tokens for `access_token`
3. Rotate API keys and tokens regularly
4. Restrict MongoDB IP whitelist in production
5. Consider using Terraform Cloud for state management

## Support

- Render Documentation: [render.com/docs](https://render.com/docs)
- Terraform Render Provider: [registry.terraform.io/providers/render-oss/render](https://registry.terraform.io/providers/render-oss/render/latest/docs)
- Beats API Issues: [github.com/lanterno/beats/issues](https://github.com/lanterno/beats/issues)
