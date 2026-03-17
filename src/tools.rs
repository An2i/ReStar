use crate::types::ToolCall;
use anyhow::Result;
use encoding_rs::GBK;
use std::path::Path;
use std::process::Command;

pub struct ToolExecutor {
    pub ida_path: String,
    pub target_path: String,
    pub script_dir: String,
}

fn decode_output(bytes: &[u8]) -> String {
    match std::str::from_utf8(bytes) {
        Ok(s) => s.to_string(),
        Err(_) => {
            let (decoded, _, _) = GBK.decode(bytes);
            decoded.into_owned()
        }
    }
}

impl ToolExecutor {
    pub fn new(target_path: String, ida_path: String) -> Self {
        let target_dir = Path::new(&target_path)
            .parent()
            .unwrap_or(Path::new("."))
            .to_string_lossy()
            .to_string();

        Self {
            ida_path,
            target_path,
            script_dir: target_dir,
        }
    }

    pub fn execute(&self, tool_call: &ToolCall) -> Result<String> {
        match tool_call.function_name.as_str() {
            "software_analysis" => self.run_software_analysis(&tool_call.arguments),
            "generate_report" => self.run_generate_report(&tool_call.arguments),
            other => Err(anyhow::anyhow!("Unknown tool: {}", other)),
        }
    }

    fn run_software_analysis(&self, args: &serde_json::Value) -> Result<String> {
        let script_name = args["ScriptFileName"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing ScriptFileName"))?;
        let code = args["Code"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing Code"))?;

        let script_path = Path::new(&self.script_dir).join(script_name);
        std::fs::write(&script_path, code)?;

        let output = Command::new(&self.ida_path)
            .args([
                "-A",
                "-B",
                &format!("-S{}", script_path.display()),
                &self.target_path,
            ])
            .output()?;

        let stdout = decode_output(&output.stdout);
        let stderr = decode_output(&output.stderr);
        let combined = format!("stdout:\n{}\nstderr:\n{}", stdout, stderr);

        Ok(combined)
    }

    fn run_generate_report(&self, args: &serde_json::Value) -> Result<String> {
        let filename = args["ReportFileName"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing ReportFileName"))?;
        let content = args["Content"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing Content"))?;

        let report_path = Path::new(&self.script_dir).join(filename);
        std::fs::write(&report_path, content)?;

        Ok(format!("Report saved to: {}", report_path.display()))
    }
}
