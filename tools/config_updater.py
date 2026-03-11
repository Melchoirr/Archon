"""Agent 可调用的 config.yaml 更新工具"""
import yaml


def update_config_section(section: str, data: str, config_path: str = "config.yaml") -> str:
    """更新 config.yaml 的指定 section

    Args:
        section: 要更新的顶层 key，如 "datasets", "metrics", "experiment"
        data: YAML 格式字符串，将被解析后写入该 section
        config_path: config.yaml 路径

    Returns:
        操作结果描述
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    parsed = yaml.safe_load(data)
    config[section] = parsed

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return f"Updated config.yaml section '{section}' successfully."


UPDATE_CONFIG_SECTION_SCHEMA = {
    "description": "更新 config.yaml 的指定 section（如 datasets, metrics, experiment）。data 参数为 YAML 格式字符串。",
    "parameters": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": "要更新的顶层 key，如 datasets, metrics, experiment",
            },
            "data": {
                "type": "string",
                "description": "YAML 格式字符串，解析后写入该 section",
            },
        },
        "required": ["section", "data"],
    },
}
