# Qwen Trading LoRA Ollama Export

This workflow converts the trained PEFT LoRA adapter into an Ollama model.

Run on Colab L4 or better. The local machine can run the final quantized GGUF,
but should not merge Qwen 7B with the adapter.

Colab command:

```python
!pip -q install -r requirements-export-colab.txt

!python export_lora_to_ollama_colab.py \
  --base-model Qwen/Qwen2.5-7B-Instruct \
  --adapter-dir qwen_trading_lora_v002_complete_market_structure_L4 \
  --work-dir /content/drive/MyDrive/QuantLLMBot/ollama_export/qwen_trading_v002 \
  --outfile-prefix qwen-trading-v002 \
  --quant Q4_K_M
```

After export, zip:

```python
!zip -r /content/drive/MyDrive/QuantLLMBot/ollama_export/qwen_trading_v002_ollama.zip \
  /content/drive/MyDrive/QuantLLMBot/ollama_export/qwen_trading_v002/ollama_model
```

Local import:

```powershell
cd <unzipped ollama_model folder>
ollama create qwen-trading-v002 -f Modelfile
ollama run qwen-trading-v002
```
