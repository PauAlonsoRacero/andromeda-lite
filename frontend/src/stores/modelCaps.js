// Espejo cliente de model_catalog.supports_tools (backend). Mantener en sync.
const CAPABLE = ['qwen2.5','qwen3','qwen2','qwq','llama3.1','llama3.2','llama3.3',
  'llama-3.1','llama-3.2','llama-3.3','mistral','mixtral','ministral','mathstral',
  'command-r','command-a','hermes3','nous-hermes2','firefunction','granite3',
  'granite-3','nemotron','deepseek-coder-v2','deepseek-v2','deepseek-v3','deepseek-r1',
  'phi4','phi-4','smollm2','codestral']
const INCAPABLE = ['embed','embedding','bge','nomic','minilm','e5-','llava','bakllava',
  'moondream','llama2','llama-2','codellama','tinyllama','tinydolphin','orca-mini',
  'vicuna','alpaca','stablelm2:1','gemma:2b','phi:']

export function supportsTools(name) {
  if (!name) return false
  const n = name.toLowerCase()
  if (INCAPABLE.some(b => n.includes(b))) return false
  if (CAPABLE.some(g => n.includes(g))) return true
  const mb = n.match(/(\d+(?:\.\d+)?)\s*b/)
  if (mb && parseFloat(mb[1]) < 3 && !n.includes('coder') && !n.includes('code')) return false
  return true
}
