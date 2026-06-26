import * as cdk from "aws-cdk-lib";
import * as apigatewayv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as apigatewayv2_integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as cloudfront_origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Construct } from "constructs";
import * as path from "path";

export interface MultiModelRouterStackProps extends cdk.StackProps {
  /** Enable verbose CloudWatch dashboard (default: true) */
  enableDashboard?: boolean;
  /** Lambda log retention (default: 7 days) */
  logRetention?: logs.RetentionDays;
  /** AWS geography for cross-region inference profiles: "us", "eu", "ap" (default: auto-detected from region) */
  geography?: string;
}

export class MultiModelRouterStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: MultiModelRouterStackProps = {}) {
    super(scope, id, props);

    const enableDashboard = props.enableDashboard ?? true;
    const logRetention = props.logRetention ?? logs.RetentionDays.ONE_WEEK;

    // ─── Lambda Execution Role ───────────────────────────────────────────
    const lambdaRole = new iam.Role(this, "RouterLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "Execution role for the multi-model LLM router Lambda",
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    // Bedrock permissions: limit to foundation models and inference profiles the router uses
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
        ],
        resources: [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*",
        ],
      })
    );

    // CloudWatch metrics permissions for custom metrics
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["cloudwatch:PutMetricData"],
        resources: ["*"],
      })
    );

    // ─── Lambda Function ─────────────────────────────────────────────────
    const routerFunction = new lambda.Function(this, "RouterFunction", {
      runtime: lambda.Runtime.PYTHON_3_13,
      code: lambda.Code.fromAsset(
        path.join(__dirname, "..", "lambda-router")
      ),
      handler: "index.lambda_handler",
      role: lambdaRole,
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      logRetention,
      description:
        "Multi-model LLM router — classifies prompt complexity and routes to Bedrock with cross-region inference",
      environment: {
        // AWS_REGION is set automatically by Lambda runtime
        AWS_GEOGRAPHY: props.geography ?? process.env.AWS_GEOGRAPHY ?? "",
        // --- Simple tier ---
        TIER_SIMPLE_CONFIG: process.env.TIER_SIMPLE_CONFIG ?? "",
        TIER_SIMPLE_PROVIDER: process.env.TIER_SIMPLE_PROVIDER ?? "",
        TIER_SIMPLE_MODEL_ID: process.env.TIER_SIMPLE_MODEL_ID ?? "",
        TIER_SIMPLE_INFERENCE_PROFILE: process.env.TIER_SIMPLE_INFERENCE_PROFILE ?? "",
        TIER_SIMPLE_API_BASE: process.env.TIER_SIMPLE_API_BASE ?? "",
        TIER_SIMPLE_API_KEY: process.env.TIER_SIMPLE_API_KEY ?? "",
        // --- Medium tier ---
        TIER_MEDIUM_CONFIG: process.env.TIER_MEDIUM_CONFIG ?? "",
        TIER_MEDIUM_PROVIDER: process.env.TIER_MEDIUM_PROVIDER ?? "",
        TIER_MEDIUM_MODEL_ID: process.env.TIER_MEDIUM_MODEL_ID ?? "",
        TIER_MEDIUM_INFERENCE_PROFILE: process.env.TIER_MEDIUM_INFERENCE_PROFILE ?? "",
        TIER_MEDIUM_API_BASE: process.env.TIER_MEDIUM_API_BASE ?? "",
        TIER_MEDIUM_API_KEY: process.env.TIER_MEDIUM_API_KEY ?? "",
        // --- Hard tier ---
        TIER_HARD_CONFIG: process.env.TIER_HARD_CONFIG ?? "",
        TIER_HARD_PROVIDER: process.env.TIER_HARD_PROVIDER ?? "",
        TIER_HARD_MODEL_ID: process.env.TIER_HARD_MODEL_ID ?? "",
        TIER_HARD_INFERENCE_PROFILE: process.env.TIER_HARD_INFERENCE_PROFILE ?? "",
        TIER_HARD_API_BASE: process.env.TIER_HARD_API_BASE ?? "",
        TIER_HARD_API_KEY: process.env.TIER_HARD_API_KEY ?? "",
      },
    });

    // ─── API Gateway HTTP API ────────────────────────────────────────────
    const httpApi = new apigatewayv2.HttpApi(this, "RouterHttpApi", {
      description: "Multi-model LLM router — POST /invoke, GET /health",
      corsPreflight: {
        allowOrigins: ["*"],
        allowMethods: [
          apigatewayv2.CorsHttpMethod.GET,
          apigatewayv2.CorsHttpMethod.POST,
          apigatewayv2.CorsHttpMethod.OPTIONS,
        ],
        allowHeaders: [
          "Content-Type",
          "X-Api-Key",
          "Authorization",
        ],
        maxAge: cdk.Duration.days(1),
      },
    });

    // Lambda integration
    const lambdaIntegration =
      new apigatewayv2_integrations.HttpLambdaIntegration(
        "RouterIntegration",
        routerFunction
      );

    // Routes
    httpApi.addRoutes({
      path: "/invoke",
      methods: [apigatewayv2.HttpMethod.POST],
      integration: lambdaIntegration,
    });
    httpApi.addRoutes({
      path: "/health",
      methods: [apigatewayv2.HttpMethod.GET],
      integration: lambdaIntegration,
    });

    // ─── Frontend: S3 + CloudFront ───────────────────────────────────────
    const frontendBucket = new s3.Bucket(this, "FrontendBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      enforceSSL: true,
    });

    const originAccessIdentity = new cloudfront.OriginAccessIdentity(
      this,
      "FrontendOAI"
    );
    frontendBucket.grantRead(originAccessIdentity);

    const distribution = new cloudfront.Distribution(this, "FrontendDistro", {
      defaultBehavior: {
        origin: new cloudfront_origins.S3Origin(frontendBucket, {
          originAccessIdentity,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      defaultRootObject: "index.html",
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: "/index.html",
        },
      ],
    });

    // Deploy frontend files
    new s3deploy.BucketDeployment(this, "FrontendDeploy", {
      sources: [s3deploy.Source.asset(path.join(__dirname, "..", "frontend"))],
      destinationBucket: frontendBucket,
      distribution,
      distributionPaths: ["/*"],
    });

    // ─── Outputs ─────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "ApiEndpoint", {
      value: httpApi.apiEndpoint,
      description: "API Gateway HTTP API endpoint",
    });
    new cdk.CfnOutput(this, "InvokeUrl", {
      value: `${httpApi.apiEndpoint}/invoke`,
      description: "POST /invoke endpoint URL",
    });
    new cdk.CfnOutput(this, "HealthUrl", {
      value: `${httpApi.apiEndpoint}/health`,
      description: "GET /health endpoint URL",
    });
    new cdk.CfnOutput(this, "LambdaName", {
      value: routerFunction.functionName,
      description: "Lambda function name",
    });
    new cdk.CfnOutput(this, "FrontendUrl", {
      value: `https://${distribution.distributionDomainName}`,
      description: "Frontend dashboard URL",
    });
    new cdk.CfnOutput(this, "BucketName", {
      value: frontendBucket.bucketName,
      description: "Frontend S3 bucket name",
    });

    // ─── CloudWatch Dashboard ────────────────────────────────────────────
    if (enableDashboard) {
      this.createDashboard(routerFunction, httpApi);
    }
  }

  /**
   * Create a CloudWatch dashboard with invocation metrics per tier,
   * latency, error rates, and cost estimates.
   */
  private createDashboard(
    fn: lambda.IFunction,
    api: apigatewayv2.IHttpApi
  ): void {
    const region = this.region;
    const functionName = fn.functionName;

    const dashboard = new cloudwatch.Dashboard(this, "RouterDashboard", {
      dashboardName: `MultiModelRouter-${this.stackName}`,
    });

    // --- Row 1: Invocation count + Errors ---
    const totalInvocations = fn.metricInvocations({
      label: "Invocations",
      dimensionsMap: { FunctionName: functionName },
    });
    const errors = fn.metricErrors({
      label: "Errors",
      dimensionsMap: { FunctionName: functionName },
    });

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: "Invocations & Errors",
        left: [totalInvocations],
        right: [errors],
        width: 12,
        period: cdk.Duration.minutes(5),
        statistic: "Sum",
      })
    );

    // --- Row 2: Latency + Throttles ---
    const duration = fn.metricDuration({
      label: "Duration (p50)",
      statistic: "p50",
    });
    const durationP99 = fn.metricDuration({
      label: "Duration (p99)",
      statistic: "p99",
    });
    const throttles = fn.metricThrottles({
      label: "Throttles",
    });

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: "Latency & Throttles",
        left: [duration, durationP99],
        right: [throttles],
        width: 12,
        period: cdk.Duration.minutes(5),
      })
    );

    // --- Row 3: Cost estimate widget (text) ---
    dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown: [
          "## 💰 Cost Estimation",
          "",
          "Per 1K invocations (estimated):",
          "",
          "| Tier | Model | Input (1K tok) | Output (1K tok) | ~Cost/1K req |",
          "|------|-------|----------------|-----------------|-------------|",
          "| Simple | Claude 3.5 Haiku | $0.25 | $1.25 | ~$1.50 |",
          "| Medium | Claude Sonnet 4 | $3.00 | $15.00 | ~$18.00 |",
          "| Hard | Claude Opus 4.8 | $10.00 | $50.00 | ~$60.00 |",
          "",
          "> Costs vary by actual token usage. Update as needed.",
          "",
          "**Cost optimization tip**: 60-70% of requests typically route to Simple,",
          "25-30% to Medium, and 5-10% to Hard. Review your distribution and",
          "adjust thresholds accordingly.",
        ].join("\n"),
        width: 24,
        height: 6,
      })
    );

    // --- Alarms ---
    new cloudwatch.Alarm(this, "HighErrorRate", {
      metric: fn.metricErrors(),
      threshold: 5,
      evaluationPeriods: 3,
      datapointsToAlarm: 2,
      alarmDescription:
        "Multi-model router error rate > 5% over 3 consecutive periods",
    });

    new cloudwatch.Alarm(this, "HighLatency", {
      metric: fn.metricDuration({ statistic: "p99" }),
      threshold: 30_000,
      evaluationPeriods: 2,
      datapointsToAlarm: 1,
      alarmDescription:
        "Multi-model router p99 latency > 30s",
    });
  }
}
