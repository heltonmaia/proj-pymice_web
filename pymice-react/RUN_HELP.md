# 🚀 Script Unificado - run.sh / run.bat

Um único script para controlar toda a aplicação!

## 📖 Uso Rápido

### Linux/Mac
```bash
./run.sh start    # Iniciar tudo
./run.sh status   # Ver status
./run.sh stop     # Parar tudo
./run.sh restart  # Reiniciar
```

### Windows
```cmd
run.bat start    # Iniciar tudo
run.bat status   # Ver status
run.bat stop     # Parar tudo
run.bat restart  # Reiniciar
```

## 📋 Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `start` | Inicia Backend + Frontend |
| `stop` | Para todos os serviços |
| `status` | Mostra status dos serviços |
| `restart` | Para e inicia novamente |
| `help` | Mostra ajuda |

## 🎯 Exemplos de Uso

### Primeiro Uso

```bash
# Dar permissão (apenas primeira vez - Linux/Mac)
chmod +x run.sh

# Iniciar
./run.sh start
```

**O que acontece:**
1. ✅ Verifica Python e Node.js
2. ✅ Cria ambiente virtual (se não existir)
3. ✅ Instala dependências (se necessário)
4. ✅ Inicia Backend na porta 8000
5. ✅ Inicia Frontend na porta 3000
6. ✅ Abre navegador automaticamente
7. 📊 Mostra informações de acesso

### Ver se está Rodando

```bash
./run.sh status
```

**Output:**
```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║           PyMiceTracking Web - Control Script                  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

📊 Status dos Serviços:

   Backend:  ● RODANDO (porta 8000)
             PID: 12345
   Frontend: ● RODANDO (porta 3000)
             PID: 12346

📱 URLs:
   Frontend:    http://localhost:5173
   Backend API: http://localhost:8000
   API Docs:    http://localhost:8000/docs

📝 Logs:
   Backend:  tail -f logs/backend.log
   Frontend: tail -f logs/frontend.log
```

### Parar Serviços

```bash
./run.sh stop
```

**O que acontece:**
1. Para processo do Backend
2. Para processo do Frontend
3. Limpa arquivos PID
4. Verifica portas (fallback)

### Reiniciar (após mudanças no código)

```bash
./run.sh restart
```

## 📁 Estrutura de Logs

Os logs são salvos em:
```
logs/
├── backend.log      # Logs do FastAPI
├── backend.pid      # PID do Backend
├── frontend.log     # Logs do Vite/React
└── frontend.pid     # PID do Frontend
```

### Ver Logs em Tempo Real

```bash
# Backend
tail -f logs/backend.log

# Frontend
tail -f logs/frontend.log

# Ambos
tail -f logs/*.log
```

## 🔧 Resolução de Problemas

### Script não executa (Linux/Mac)

```bash
chmod +x run.sh
./run.sh start
```

### Porta já em uso

O script detecta automaticamente e mata o processo antigo:

```bash
./run.sh start
# Se porta em uso, vai matar processo automaticamente
```

### Dependências não instaladas

```bash
# O script instala automaticamente na primeira execução
./run.sh start

# Ou force reinstalação deletando:
rm -rf backend/venv
rm -rf frontend/node_modules
./run.sh start  # Irá reinstalar tudo
```

### Serviço não para

```bash
# Use stop duas vezes
./run.sh stop
./run.sh stop

# Ou mate manualmente
kill $(lsof -t -i:8000)  # Backend
kill $(lsof -t -i:3000)  # Frontend
```

### Verificar se portas estão livres

```bash
# Linux/Mac
lsof -i :8000
lsof -i :3000

# Windows
netstat -ano | findstr :8000
netstat -ano | findstr :3000
```

## 💡 Dicas

1. **Sempre use `status` antes de `start`** para evitar duplicação
2. **Use `restart` após mudanças** no código Python
3. **Frontend tem hot-reload** - não precisa restart para mudanças React
4. **Logs são seus amigos** - sempre verifique em caso de erro
5. **Use Ctrl+C nos logs** para sair da visualização

## 🎓 Fluxo de Trabalho Típico

```bash
# Manhã - Iniciar trabalho
./run.sh start

# Desenvolvimento...
# (Frontend atualiza automaticamente)
# (Backend precisa restart se mudar código)

# Após mudança no Backend
./run.sh restart

# Ver se está tudo ok
./run.sh status

# Verificar erros
tail -f logs/backend.log

# Final do dia
./run.sh stop
```

## 📊 Comparação com Scripts Anteriores

| Recurso | run.sh | start.sh + stop.sh + dev.sh |
|---------|--------|---------------------------|
| Comandos | 1 script | 3 scripts |
| Start | ✅ | ✅ |
| Stop | ✅ | ✅ |
| Status | ✅ | ❌ (só dev.sh) |
| Restart | ✅ | ❌ |
| Simples | ✅✅✅ | ✅ |

**run.sh = Tudo em um só lugar!** 🎯

## 🌟 Recursos do Script

- ✅ Auto-detecção de dependências
- ✅ Instalação automática (primeira vez)
- ✅ Gestão de PIDs
- ✅ Logs centralizados
- ✅ Verificação de portas
- ✅ Fallback automático
- ✅ Abre navegador
- ✅ Output colorido e informativo
- ✅ Cross-platform (Linux/Mac/Windows)

---

**Use: `./run.sh help` para ver ajuda!** 📚
