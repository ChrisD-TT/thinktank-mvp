$folder = "$HOME\linkedin_profile"

New-Item -ItemType Directory -Force -Path $folder | Out-Null

@"
AI Solutions Specialist | Founder, ThinkTank A.I. | Enterprise Workflow Automation | AI Evaluation | Generative AI
"@ | Set-Content "$folder\headline.txt"

@"
Founder and AI Solutions Developer
ThinkTank A.I.
November 2025 - Present

Founded and developed ThinkTank A.I., focused on practical applications of artificial intelligence, workflow automation, enterprise productivity, and knowledge management.

- Designed AI-assisted workflows
- Evaluated AI-generated outputs
- Developed prompt engineering methodologies
- Researched enterprise AI adoption
- Created structured knowledge systems
- Investigated emerging AI technologies
"@ | Set-Content "$folder\experience.txt"

@"
Artificial Intelligence
Generative AI
Prompt Engineering
AI Evaluation
Workflow Automation
Microsoft Copilot
Enterprise Productivity
Knowledge Management
Problem Solving
Research and Analysis
"@ | Set-Content "$folder\skills.txt"

Write-Host "LinkedIn files created successfully!" -ForegroundColor Green

Invoke-Item $folder