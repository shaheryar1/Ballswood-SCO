import yaml

# Open the YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

print(config["input_rtsp_streams"]["76"]["stream"])
