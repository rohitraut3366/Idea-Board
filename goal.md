Case Study: Building an AI-First,
Cloud-Agnostic DevOps Platform

1. Introduction
Welcome! This case study is designed to assess your ability to design, implement, and manage a
modern, automated, and intelligent DevOps platform. The goal is not just to test your knowledge of
specific tools, but to see how you approach complex problems, think about system architecture, and
creatively apply AI to improve the software development lifecycle.
Your task is to build a simple full-stack application and then design and build a sophisticated,
AI-enhanced deployment pipeline for it, focusing on cloud-agnostic principles and AI-driven
automation.
2. The Challenge

Part 1: Build "The Idea Board" Application
First, you must create a simple "Idea Board" application. The application should be composed of
three distinct parts. You have the freedom to choose your preferred libraries and frameworks, but
here is a recommended stack:
● Frontend: A React application that displays a list of ideas and has a form to submit new
ones.
● Backend: A Python (FastAPI is recommended) application providing a simple REST API.
○ GET /api/ideas: Returns a JSON array of all ideas.
○ POST /api/ideas: Accepts a JSON object like {"content": "My new idea"}
and stores it.

● Database: A PostgreSQL database with a single ideas table (id, content, created_at).
The functionality should be basic. The focus of this case study is on the platform you build to deploy
this application.
Part 2: Containerize Everything
● Create a Dockerfile for your React frontend.
● Create a Dockerfile for your Python backend.
● Create a docker-compose.yml file to easily run the entire stack (frontend, backend,
database) for local development.

Part 3: Cloud-Agnostic Infrastructure as Code (IaC)
● Choose an IaC tool (Terraform is recommended, but Pulumi or others are acceptable).
● Write modular and reusable IaC to provision the necessary infrastructure to run your
application. This should include:
○ A container orchestration service (e.g., Kubernetes - EKS, GKE, AKS).
○ A managed PostgreSQL database (e.g., AWS RDS, Google Cloud SQL).
○ Necessary networking and security configurations.
● Your IaC must be designed to be cloud-agnostic. You should be able to deploy the stack to
at least two major cloud providers (e.g., AWS and GCP) by changing only a few
configuration variables.
Part 4: The AI-Powered CI/CD Pipeline
This is the most creative part of the challenge. Design and implement a CI/CD pipeline (using
GitHub Actions, GitLab CI, or your tool of choice) that intelligently automates and enhances the
deployment process by leveraging AI.
We are looking for original thinking, but here are some ideas to spark your imagination:
● AI-Assisted Command Generation: Can you use an LLM to generate deployment
commands (kubectl apply, shell scripts, etc.) based on natural language inputs or git
branch names? For example, a PR comment like /deploy-preview feature-x could
trigger a pipeline that asks an AI to generate the steps for a preview deployment.
● Dynamic Environment Configuration: Use an AI to propose or generate infrastructure
configurations (e.g., instance types, replica counts, scaling policies) based on high-level
goals. For example, a developer could specify a "cost-sensitive staging" environment versus
a "high-availability production" environment.
● Intelligent Health Checks & Rollbacks: After a deployment, use an AI to analyze
application logs and metrics to determine if the deployment is healthy. If it detects anomalies,
it could trigger an automatic rollback and provide a human-readable summary of the issue.
● Generative IaC: Could part of your pipeline involve an AI generating or modifying the IaC for
a new microservice or environment based on a simple specification file?
Part 5: Deployment & Verification
● Successfully deploy the full application stack to two different cloud providers of your choice
(e.g., AWS and Azure, or GCP and DigitalOcean).
● Ensure the deployed applications are publicly accessible.
3. Deliverables
1. A link to your public Git repository containing all your work.

2. The repository's README.md must be comprehensive and include:
○ A clear, high-level explanation of your architecture.
○ Step-by-step instructions on how to run your project locally using Docker Compose.
○ Step-by-step instructions on how to configure and run your pipeline to deploy the
application to a cloud provider.
○ A detailed section on your AI Integration. Explain what you built, the design choices
you made, and how your AI-powered features provide tangible value to the DevOps
lifecycle.
○ A section on your Cloud-Agnostic Approach. Explain the design of your IaC and
pipeline that enables seamless multi-cloud deployment.

3. Provide the working URLs for your application deployed on two different cloud providers.
4. Evaluation Criteria

You will be evaluated on:
● Technical Excellence: Is your solution robust, secure, and scalable? Does it follow best
practices?
● Cloud-Agnosticism: How effectively have you abstracted away cloud-specific details? How
easy would it be to add a third cloud provider?
● AI Innovation: How creative, practical, and valuable is your use of AI? Does it solve a
real-world problem or just a gimmick?
● Code Quality: Is your code (application code, IaC, pipeline configs, scripts) clean,
well-organized, and reusable?
● Clarity: How well is your work documented and explained?
Good luck! We are excited to see what you build.