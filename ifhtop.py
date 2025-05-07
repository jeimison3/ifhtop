import argparse
import curses.textpad
import signal
import time
import subprocess
import json
import os.path
import copy

# print(ethtool.__file__)
parser = argparse.ArgumentParser()
parser.add_argument("-i","--interface", help="Nome da interface", default="")
parser.add_argument("-c","--config", help="Arquivo de configuração", default="ifparam.json")
parser.add_argument("-d","--delay", type=int, help="Intervalo de atualização (default=10)", default=10)
parser.add_argument("-a","--amostras", type=int, help="Número de amostras (1/seg) (default=60)", default=60)
args = parser.parse_args()

unidadesPps = ['pps','Kpps','Mpps','Gpps','Tpps']
unidadesBps = ['bps','Kbps','Mbps','Gbps','Tbps']

if not args.interface:
    print("ERRO: Interface [-i] mandatória.")
    exit()
params = {}
stats = []
config_filename = args.config
if os.path.exists(config_filename):
    try:
        with open(config_filename, 'r') as file:
            params = json.load(file)
            stats = params['estatisticas']
    except FileNotFoundError:
        print(f"ERRO: File not found: {config_filename}")
    except json.JSONDecodeError:
        print(f"ERRO: Invalid JSON format in: {config_filename}")
else:
    print(f"ERRO: Arquivo de configuração [-c] \"{config_filename}\" não encontrado.")

finalizar = False
interface = args.interface
def _exit_gracefully(p1, p2):
    global finalizar
    finalizar = True
signal.signal(signal.SIGINT, _exit_gracefully)
signal.signal(signal.SIGTERM, _exit_gracefully)

import curses

def main(stdscr : curses.window):
    global finalizar, stats, args
    max_y,max_x = stdscr.getmaxyx()
    curses.halfdelay(args.delay)
    curses.noecho()
    lastRun = time.time()
    tabela = {}
    amostras = []
    
    while not finalizar:
        try:
            saida = subprocess.check_output(['ethtool', '-S', interface], stderr=subprocess.PIPE)
            linhas = saida.decode("utf-8").split('\n')
            for linha in linhas:
                for param in stats:
                    if linha.find(param) != -1:
                        valor = linha.split(':')[1].strip()
                        if valor.isnumeric():
                            if not interface in tabela:
                                tabela[interface] = {}
                            tabela[interface][param] = int(valor)
        except Exception as e:
            pass
        
        amostras.append(copy.deepcopy(tabela))
        if(len(amostras) > args.amostras):
            amostras.pop(0)
        graficos = {}
        for idAmostra,registro in enumerate(amostras):
            if idAmostra == 0: continue
            for eth in registro:
                for key in stats:
                    nome = "{} {}".format(eth,key)
                    if not (nome in graficos):
                        graficos[nome] = []
                    graficos[nome].append(amostras[idAmostra][eth][key]-amostras[idAmostra-1][eth][key])
        
        # print("\n"*4)
        stdscr.clear()
        lastRow = 2
        for eth in tabela:
            stdscr.addstr(0, 0, "Interface: {}".format(eth), curses.A_REVERSE)
            stdscr.addstr(0, 40, "Intervalo: {} ms".format(int(((time.time()-lastRun)*1000))), curses.A_REVERSE)
            for chave in stats:
                if chave+'_old' in tabela[eth]:
                    pps = int(tabela[eth][chave]-tabela[eth][chave+'_old'])
                    if chave.find('bytes')!=-1:
                        pps *= 8
                    unidade = 0
                    while pps > 1000:
                        unidade+=1
                        pps /= 1000
                    lastRow += 1
                    stdscr.addstr(lastRow, 2, "{} =".format(chave))
                    stdscr.addstr(lastRow, 18, "{:.2f} {}".format(pps//(time.time()-lastRun), unidadesPps[unidade] if chave.find('bytes')==-1  else unidadesBps[unidade]))
                tabela[eth][chave+'_old'] = tabela[eth][chave]
        
        lastRow+=2
        
        lastRowOnStart = lastRow
        usosPorGrafico = 0
        colBase = 0
        
        for nomeGrafico in graficos:
            if usosPorGrafico > 0:
                if lastRow+usosPorGrafico > max_y:
                    # try:
                    #     stdscr.addstr(lastRow,colBase+4,'encerrado por falta de linhas', curses.A_REVERSE)
                    # except Exception as e:
                    #     pass
                    # break
                    colBase += 2+1+args.amostras + 8
                    lastRow = lastRowOnStart
            usosPorGrafico = lastRow
            maxValor = 0
            for valor in graficos[nomeGrafico]:
                if valor > maxValor:
                    maxValor = valor
            # Apresentação
            # > Maximo:
            maxValorPresent = maxValor
            if nomeGrafico.find('bytes')!=-1:
                maxValorPresent *= 8
            maxValorUnidade = 0
            while maxValorPresent > 1000:
                maxValorUnidade+=1
                maxValorPresent //= 1000
            # > Atual:
            atualValorPresent = graficos[nomeGrafico][-1]
            if nomeGrafico.find('bytes')!=-1:
                atualValorPresent *= 8
            atualValorUnidade = 0
            while atualValorPresent > 1000:
                atualValorUnidade+=1
                atualValorPresent //= 1000
                
                
            try:
                stdscr.addstr(lastRow, colBase+2, "====== {} ====== | Max = {} {} | Curr= {} {}".format(
                    nomeGrafico,
                    maxValorPresent, unidadesBps[maxValorUnidade] if nomeGrafico.find('bytes')!=-1 else unidadesPps[maxValorUnidade],
                    atualValorPresent, unidadesBps[atualValorUnidade] if nomeGrafico.find('bytes')!=-1 else unidadesPps[atualValorUnidade]
                ))
            except Exception as e:
                pass
            lastRow+=1 # Quebra de linha
            graphLines = 8
            
            maxValor=maxValor*1.1 #+10%
            try:
                curses.textpad.rectangle(stdscr, lastRow, colBase+2, lastRow+graphLines, colBase+2+1+args.amostras)
            except Exception as e:
                pass
            lastRow+=graphLines
            
            for _registro in range(len(graficos[nomeGrafico])-1, -1, -1):
                colPos = 2 + args.amostras - len(graficos[nomeGrafico]) + _registro# Posicao verdadeira
                
                registroLevel = int(graphLines*(graficos[nomeGrafico][_registro]/(maxValor if maxValor > 0 else 1)))
                for yUp in range(registroLevel):
                    stdscr.addch(lastRow-yUp-1, colBase+colPos,' ', curses.A_REVERSE)
            
            lastRow+=2
            usosPorGrafico = lastRow-usosPorGrafico
            # break
        
        lastRun = time.time()
        stdscr.move(1,0)
        stdscr.refresh()
        char = stdscr.getch()
        if char != curses.ERR:
            if chr(char) == 'q':
                finalizar = True
    return "Finalizado com sucesso."
    
    
print(curses.wrapper(main))