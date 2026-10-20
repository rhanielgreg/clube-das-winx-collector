"""Diagnostico seguro de conectividade e autenticacao SFTP (BisectHosting).

Execucao controlada e segura:
- Testa em etapas separadas:
  1. Resolucao DNS e porta TCP
  2. Negociacao SSH, banner e chave do servidor (known_hosts)
  3. Metodos de autenticacao aceitos pelo servidor remoto
  4. Formato das credenciais locais (tamanho, espacos, caracteres de controle)
  5. Teste unico e pontual de autenticacao por senha (sem loops repetidos)
  6. Se autenticar: listagem restrita do diretorio do players.db
- Nao exibe senhas, tokens ou chaves em nenhum log ou console.
- Nao altera credenciais.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import typing

try:
    import paramiko
except ImportError:
    print('ERRO: paramiko nao esta instalado no ambiente atual.')
    sys.exit(1)


def mask_middle(text: str, keep_start: int = 3, keep_end: int = 3) -> str:
    if not text:
        return '<vazio>'
    if len(text) <= keep_start + keep_end:
        return '*' * len(text)
    return f'{text[:keep_start]}...{text[-keep_end:]}'


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    vars_found: dict[str, str] = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line_clean = line.strip()
            if not line_clean or line_clean.startswith('#'):
                continue
            if '=' in line_clean:
                k, v = line_clean.split('=', 1)
                k = k.strip()
                v = v.strip()
                # Remove aspas externas se existirem
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                vars_found[k] = v
    return vars_found


def get_conf(key: str, env_dict: dict[str, str], default: str = '') -> str:
    return os.getenv(key) or env_dict.get(key, default)


def run_diagnostics(attempt_auth: bool = False) -> None:
    print('=' * 65)
    print('  DIAGNOSTICO SFTP — CLUBE DAS WINX (BISECTHOSTING)')
    print('=' * 65)

    # 1. Carregamento das variaveis
    env_local = Path(__file__).resolve().parent / '.env.local'
    file_vars = load_env_file(env_local)
    source = f'.env.local ({env_local.name})' if env_local.is_file() else 'Variaveis de ambiente do sistema'
    print(f'[*] Fonte de configuracao: {source}')

    host = get_conf('SFTP_HOST', file_vars)
    port_str = get_conf('SFTP_PORT', file_vars, '2022')
    user = get_conf('SFTP_USER', file_vars)
    password = get_conf('SFTP_PASSWORD', file_vars)
    known_hosts_line = get_conf('SFTP_KNOWN_HOSTS', file_vars)
    db_path = get_conf('SFTP_DB_PATH', file_vars)

    try:
        port = int(port_str)
    except ValueError:
        print(f'[-] ERRO: SFTP_PORT invalida: {port_str}')
        return

    print('\n[1] Analise estatica das variaveis:')
    print(f'  • Host: {mask_middle(host, 4, 4)} (tamanho: {len(host)})')
    print(f'  • Porta: {port}')
    print(f'  • Usuario: {mask_middle(user, 4, 3)} (tamanho: {len(user)})')
    has_pwd = bool(password)
    pwd_len = len(password)
    print(f'  • Senha configurada: {"Sim" if has_pwd else "Nao"} (comprimento: {pwd_len} caracteres)')
    print(f'  • Caminho players.db: {db_path}')

    # Verificacoes de higienizacao de credenciais
    warnings = []
    if '#' in password:
        warnings.append('A senha contem o caractere "#". Se o arquivo .env ou o Railway interpretar sem aspas, tudo apos "#" e tratado como comentario.')
    if any(c.isspace() for c in password):
        warnings.append('A senha possui espacos em branco ou quebras de linha.')
    if '.' not in user:
        warnings.append('O usuario SFTP da BisectHosting normalmente possui formato "usuario.servidor" ou similar gerado pelo painel (Pterodactyl/Games Panel).')
    if not host or not user or not password:
        warnings.append('Alguma credencial essencial esta ausente.')

    if warnings:
        print('\n[!] Alertas de formato:')
        for w in warnings:
            print(f'  [!] {w}')
    else:
        print('  [+] Formato basico das variaveis parece estruturado.')

    # 2. Conectividade TCP
    print('\n[2] Teste de conectividade TCP:')
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        banner = sock.recv(1024).decode('utf-8', errors='replace').strip()
        sock.close()
        print(f'  [+] Conexao TCP na porta {port} bem-sucedida.')
        print(f'  [+] Banner recebido do servidor: {banner}')
    except Exception as e:
        print(f'  [-] Falha ao conectar TCP: {type(e).__name__}: {e}')
        return

    # 3. Negociacao SSH e validacao de chave (known_hosts)
    print('\n[3] Negociacao SSH e validacao de chave de host:')
    transport = None
    try:
        transport = paramiko.Transport((host, port))
        transport.start_client(timeout=15)
        server_key = transport.get_remote_server_key()
        key_type = server_key.get_name()
        key_b64 = server_key.get_base64()
        print(f'  [+] SSH negociado com sucesso.')
        print(f'  [+] Tipo de chave do servidor remoto: {key_type}')
        print(f'  [+] Fingerprint MD5: {paramiko.util.hexlify(server_key.get_fingerprint())}')

        if known_hosts_line:
            matches_known = key_b64 in known_hosts_line
            print(f'  [+] Chave remota confere com SFTP_KNOWN_HOSTS: {matches_known}')
            if not matches_known:
                print('  [-] ATENCAO: A chave publica do servidor nao bate com o valor registrado no SFTP_KNOWN_HOSTS!')
        else:
            print('  [!] SFTP_KNOWN_HOSTS nao esta definido para validacao estrita.')

        # 4. Metodos de autenticacao suportados
        print('\n[4] Metodos de autenticacao aceitos pelo servidor remoto:')
        try:
            transport.auth_none(user or 'probe_user')
            print('  [!] Servidor permitiu login sem credencial (auth_none)!')
        except paramiko.BadAuthenticationType as err:
            allowed = err.allowed_types
            print(f'  [+] Metodos aceitos pelo servidor: {allowed}')
            if 'password' in allowed:
                print('  [+] "password" e aceito pelo servidor SSH da BisectHosting.')
            else:
                print('  [-] "password" NAO consta entre os metodos aceitos!')
        except Exception as e:
            print(f'  [!] Consulta de metodos retornou: {type(e).__name__}: {e}')
    except Exception as e:
        print(f'  [-] Falha na negociacao SSH: {type(e).__name__}: {e}')
        if transport:
            transport.close()
        return
    finally:
        if transport and transport.is_active():
            transport.close()

    # 5. Teste unico e pontual de autenticacao
    print('\n[5] Teste de autenticacao com as credenciais configuradas:')
    if not attempt_auth:
        print('  [i] Teste de autenticacao omitido por padrao para evitar bloqueios de seguranca.')
        print('      Para executar UM UNICO teste de login, execute com: --test-auth')
        print('=' * 65)
        return

    print('  [*] Executando uma tentativa unica de autenticacao (sem loops)...')
    client = paramiko.SSHClient()
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            kh_file = Path(tmp_dir) / 'known_hosts'
            if known_hosts_line:
                kh_file.write_text(known_hosts_line.strip() + '\n', encoding='utf-8')
                client.load_host_keys(str(kh_file))
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                timeout=15,
                auth_timeout=15,
                banner_timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
            print('  [+] AUTENTICACAO BEM-SUCEDIDA!')

            # 6. Teste de SFTP e listagem
            print('\n[6] Teste de sessao SFTP e navegacao:')
            sftp = client.open_sftp()
            try:
                root_files = sftp.listdir('.')
                print(f'  [+] Sessao SFTP iniciada. Itens no diretorio raiz: {len(root_files)}')

                parent_dir = str(Path(db_path).parent).replace('\\', '/')
                print(f'  [*] Verificando diretorio do banco ({parent_dir})...')
                try:
                    db_dir_items = sftp.listdir(parent_dir)
                    print(f'  [+] Diretorio do banco acessivel. Total de itens: {len(db_dir_items)}')
                    db_name = Path(db_path).name
                    if db_name in db_dir_items:
                        attrs = sftp.stat(db_path)
                        print(f'  [+] {db_name} encontrado! Tamanho: {attrs.st_size} bytes, mtime: {attrs.st_mtime}')
                    else:
                        print(f'  [!] {db_name} nao foi encontrado dentro de {parent_dir}.')
                except Exception as dir_err:
                    print(f'  [-] Nao foi possivel acessar {parent_dir}: {type(dir_err).__name__}: {dir_err}')
            finally:
                sftp.close()
    except paramiko.AuthenticationException as auth_err:
        print(f'  [-] Falha na autenticacao: {type(auth_err).__name__} (Authentication failed).')
        print('      -> A senha ou usuario enviados foram rejeitados pelo servidor da BisectHosting.')
    except Exception as e:
        print(f'  [-] Erro inesperado no teste de conexao: {type(e).__name__}: {e}')
    finally:
        client.close()

    print('=' * 65)


if __name__ == '__main__':
    attempt = '--test-auth' in sys.argv
    run_diagnostics(attempt_auth=attempt)
