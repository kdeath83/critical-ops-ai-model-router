#!/usr/bin/env node
/**
 * Multi-Model LLM Router — CDK App
 *
 * Deploys:
 *   - Lambda function with prompt classifier + Bedrock router
 *   - API Gateway HTTP API
 *   - CloudWatch dashboard + alarms
 *
 * One-click deploy:
 *   npm run deploy
 *   AWS_GEOGRAPHY=eu npx cdk deploy --require-approval never
 *
 * Geography controls cross-region inference profiles:
 *   us  → us-east-1, us-east-2, us-west-2
 *   eu  → eu-west-1, eu-west-2, eu-central-1, ...
 *   ap  → ap-southeast-1, ap-northeast-1, ...
 */
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { MultiModelRouterStack } from "../lib/multi-model-router-stack";

const app = new cdk.App();

// Geography: read from CDK context (-c geography=eu) or env var
const geography = 
  app.node.tryGetContext("geography") ||
  process.env.AWS_GEOGRAPHY ||
  "";

new MultiModelRouterStack(app, "MultiModelRouter", {
  description:
        "Critical Operations AI Model Router — multi-provider load balancing for APRA-regulated critical operations (simple: Haiku, medium: Sonnet 4, complex: Opus 4.8)",
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "us-east-1",
  },
  geography,
  tags: {
    Project: "aws-multi-model-router",
    ManagedBy: "CDK",
    Environment: process.env.ENVIRONMENT || "dev",
  },
});

app.synth();
