# Agent Outlook local SmartSup

Cet agent permet au SmartSup hébergé sur Render d'ouvrir un **brouillon** dans
Outlook sur le PC Windows de l'opérateur. Il ne possède volontairement aucun
chemin d'envoi automatique.

## Pré-requis

- Windows avec Outlook desktop configuré ;
- Python 3 et les dépendances de `requirements.txt` installées ;
- Tailscale connecté sur le PC et sur l'appareil qui ouvre SmartSup ;
- le PC doit rester allumé et la session Outlook disponible.

Tailscale Serve fournit une URL HTTPS privée dans le tailnet et applique ses
ACL. Ne pas utiliser Tailscale Funnel pour cet agent.

## Installation

Dans PowerShell, depuis le dépôt :

```powershell
pip install -r requirements.txt
$token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
[Environment]::SetEnvironmentVariable("SMARTSUP_AGENT_TOKEN", $token, "User")
[Environment]::SetEnvironmentVariable("SMARTSUP_ALLOWED_ORIGIN", "https://smartsup-uz6c.onrender.com", "User")
```

Fermer puis rouvrir PowerShell, puis démarrer l'agent :

```powershell
python local_agent.py
```

Dans un second PowerShell ouvert en administrateur, publier uniquement dans le
tailnet :

```powershell
tailscale serve --https=443 http://127.0.0.1:8765
tailscale serve status
```

Tailscale affiche alors l'URL HTTPS privée du PC, de la forme
`https://nom-du-pc.tailnet.ts.net`.

## Utilisation

1. Ouvrir SmartSup depuis un appareil connecté au même tailnet.
2. Aller dans **Saisie rapide**, renseigner le ticket et le service.
3. Cliquer sur **Ouvrir Outlook local**.
4. Lors de la première utilisation de la session navigateur, saisir l'URL
   Tailscale de l'agent et le jeton généré ci-dessus.
5. Outlook ouvre le brouillon. L'opérateur relit puis choisit lui-même
   d'envoyer ou non.

Le navigateur conserve le jeton uniquement dans `sessionStorage` : il disparaît
à la fermeture de l'onglet. Le jeton n'est ni stocké dans Render ni commité
dans Git.

En secours, **Télécharger .eml** crée un fichier ouvrable dans Outlook sans
agent local.

## Exploitation

L'agent écoute exclusivement sur `127.0.0.1`. Il n'est donc pas exposé sur le
réseau local. Tailscale Serve est le seul proxy autorisé et les ACL Tailscale
doivent limiter l'accès aux opérateurs concernés.
