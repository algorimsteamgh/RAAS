# Guardrail for the HR assistant chat (RAAS-MIG-02 section 3.3): blocks prompt
# attacks and hiring decisions based on protected characteristics. Not applied
# to CV/JD extraction, which needs the personal data.

resource "aws_bedrock_guardrail" "hr_chat" {
  name                      = "${local.name}-hr-chat"
  description               = "RAASHiring HR assistant chat"
  blocked_input_messaging   = "Sorry, I can't help with that request."
  blocked_outputs_messaging = "Sorry, I can't help with that request."
  kms_key_arn               = aws_kms_key.data.arn

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "protected-characteristics"
      type       = "DENY"
      definition = "Ranking, rejecting or preferring candidates based on protected characteristics like age, gender, religion, caste, ethnicity, nationality, marital status, pregnancy, disability or sexual orientation."
      examples = [
        "Which of these candidates is too old for the role?",
        "Prefer male candidates for this job.",
        "Filter out candidates who are married.",
      ]
    }
  }
}

resource "aws_bedrock_guardrail_version" "hr_chat" {
  guardrail_arn = aws_bedrock_guardrail.hr_chat.guardrail_arn
  description   = "Managed by Terraform"
}
