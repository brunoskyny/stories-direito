# Robô de stories semanais: Departamento de Direito PUC-Rio

Toda **segunda-feira por volta das 9h (Brasília)** o robô:

1. lê as notícias recentes do site <https://direitograd.projetosjur.com/noticias>, direto do WordPress que alimenta o site;
2. considera só as das categorias de evento (palestra, seminário, evento, jornada...). Avisos como prazos e editais ficam de fora;
3. extrai do texto a data, o horário e o local (ex.: "na quarta-feira, 4 de novembro, às 10h ... Local: Auditório FB8");
4. **se não houver evento naquela semana, não publica nada;**
5. se houver, gera a arte (1080×1920, até 4 eventos por story) e publica no Instagram;
6. renova o token do Instagram toda semana, para ele nunca expirar.

---

## Parte 1: Credenciais do Instagram (≈ 15 min, uma única vez)

**Não é preciso ter Página no Facebook.** O robô usa a *API do Instagram com login do Instagram*, que funciona só com a conta profissional do Instagram.

Você só precisa de um **perfil pessoal no Facebook** (o seu) para se cadastrar como desenvolvedor na Meta. O Facebook não tem "conta de pessoa jurídica": empresas usam Páginas, administradas por perfis pessoais. Seu perfil aparece só como dono do app técnico; nada é publicado nele.

### 1.1 Cadastrar-se como desenvolvedor
1. Entre no Facebook com seu perfil pessoal e acesse <https://developers.facebook.com>.
2. Clique em **Começar / Get Started**, aceite os termos e confirme o celular e o e-mail com os códigos recebidos.

### 1.2 Criar o app
1. <https://developers.facebook.com/apps> → **Criar app**.
2. Caso de uso: **"Gerenciar mensagens e conteúdo no Instagram"**. Se não aparecer, escolha **Outro → Empresa**.
3. Nome: `Stories Direito PUC-Rio`. Conta empresarial: pode deixar **sem portfólio**.

### 1.3 Conectar o Instagram do departamento e gerar o token
1. No painel do app: **Instagram → Configuração da API com login do Instagram** (*API setup with Instagram login*).
2. Etapa **"Gerar tokens de acesso"** → **Adicionar conta** → entre com o **usuário e a senha do Instagram do departamento** e autorize.
3. Ao lado da conta, clique em **Gerar token**, copie o valor e guarde para o passo 2.4.
   É um token de 60 dias. **O robô o renova sozinho toda semana**, então ele não expira enquanto o robô estiver rodando.

> Se o Instagram pedir para aceitar um convite de testador: no app do Instagram, **Configurações → Apps e sites → Convites de testador → Aceitar**.
> Não é preciso enviar o app para revisão da Meta: ele só publica na conta que você mesmo adicionou.

**Recuperar a Página antiga do Facebook?** Não é necessário para o robô. Se quiserem recuperá-la mesmo assim, o caminho é a central de ajuda da Meta ("Não tenho acesso à minha Página"). Ter uma Página vinculada ao Instagram não atrapalha o robô.

---

## Parte 2: GitHub (≈ 15 min)

### 2.1 Criar o repositório
1. Crie uma conta em <https://github.com> (pode ser com o e-mail institucional) ou use a sua.
2. **New repository** → nome `stories-direito` → **Public** → **Create repository**.
   *Precisa ser público porque a Meta baixa a imagem do story de um endereço aberto (o robô guarda as artes no branch `stories`). Nenhuma senha ou token fica no código.*

### 2.2 Enviar os arquivos
1. Na página do repositório, clique em **uploading an existing file**.
2. Descompacte o zip e **arraste o conteúdo da pasta `story-bot`** (não a pasta em si), incluindo a pasta `.github`.
   No Mac, a `.github` fica oculta: no Finder, pressione `Cmd + Shift + .` para vê-la.
3. **Commit changes** e confira se existe `.github/workflows/story-semanal.yml`.

### 2.3 Criar a chave que deixa o robô renovar o token
1. No GitHub: foto do perfil → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Nome `robo-stories`, validade **Sem expiração** (ou 1 ano), **Only select repositories** → `stories-direito`.
3. Em **Repository permissions**, coloque **Secrets: Read and write**.
4. **Generate token** e copie o valor.

### 2.4 Cadastrar os segredos
No repositório: **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Secret |
|---|---|
| `IG_ACCESS_TOKEN` | o token do Instagram (passo 1.3) |
| `GH_PAT` | a chave do GitHub (passo 2.3) |

(`IG_USER_ID` não é mais necessário: o robô descobre a conta pelo token.)

### 2.5 Liberar escrita para o robô
**Settings → Actions → General → Workflow permissions** → **Read and write permissions** → **Save**.

---

## Parte 3: Testar

Aba **Actions** → **Story semanal de eventos** → **Run workflow**:

1. **Teste sem publicar:** `dry_run = 1`. Ao terminar, abra a execução e baixe a arte em **Artifacts**.
   Para simular uma semana com eventos, preencha `today` (ex.: `2026-11-03`).
2. **Teste real:** `dry_run = 0`. O story aparece no Instagram do departamento.

Depois disso, o agendamento semanal roda sozinho. Se a execução falhar, o GitHub envia um e-mail ao dono do repositório.

---

## Ajustes comuns (`config.yaml`)

* **Textos e cores:** seção `story:` (título, subtítulo, rodapé, cores).
* **Quais notícias viram story:** lista `event_categories:` (slugs das categorias do WordPress).
* **Horário:** linha `cron:` em `.github/workflows/story-semanal.yml` (em UTC; 11:50 UTC = 8h50 em Brasília).

## Limitações

* A data do evento é lida do texto da notícia. Se a notícia não escrever a data por extenso ("4 de novembro"), o evento não é detectado. Vale a recomendação à equipe que publica no site.
* Stories via API não aceitam figurinha de link/enquete, por isso o rodapé diz "link na bio".
* O GitHub pausa agendamentos de repositórios sem nenhuma atividade por 60 dias. Se isso acontecer, reative na aba Actions.
