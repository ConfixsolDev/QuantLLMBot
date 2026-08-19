# QuantLLMBot — agent entry

## Binding (every model / agent)

1. **Training / data / curriculum process** → use **only**  
   [`model_training/CURRICULUM_AND_DATA_PREP.md`](model_training/CURRICULUM_AND_DATA_PREP.md)  
   Do **not** create new markdown on those topics. Do **not** overlook it.

2. **Model-job Python** → read then use/extend  
   [`model_training/python_utilities_for_models/`](model_training/python_utilities_for_models/)  
   Put any new curriculum/data utility `.py` **there only**.

3. **Live system code** → [`apps/qwen_trade_software/`](apps/qwen_trade_software/) (separate).  
   **Colab train pipeline** → repo [`scripts/`](scripts/).

4. **Live doctrine** → `store/core_skill.md` + `store/sop.md` (improve, don’t inflate).

## Sole architecture authority

Use only [`XAUUSD_SYSTEM_ARCHITECTURE_V2.md`](XAUUSD_SYSTEM_ARCHITECTURE_V2.md).
It is the protected V2 architecture and must be improved in place, never
replaced by another architecture document.
