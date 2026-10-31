"""Vocabulário da base mock. Todos os nomes de lojas, marcas e transportadoras são fictícios."""

SEGMENTOS = [
    ("Moda", 30), ("Beleza & Cosméticos", 12), ("Casa & Decoração", 10), ("Eletrônicos", 8),
    ("Esporte & Fitness", 8), ("Pet Shop", 7), ("Alimentos & Bebidas", 6), ("Acessórios", 8),
    ("Infantil", 6), ("Saúde & Bem-estar", 5),
]

PERFIL_SAZONAL = {"Moda": "moda_beleza", "Beleza & Cosméticos": "moda_beleza", "Acessórios": "moda_beleza",
                  "Pet Shop": "pet"}

# segmento -> [(categoria, peso, preco_min, preco_max, [tipos de produto])]
CATALOGO = {
    "Moda": [
        ("Roupas Femininas", 30, 49, 299, ["Vestido", "Blusa", "Saia", "Calça", "Macacão"]),
        ("Roupas Masculinas", 20, 49, 249, ["Camisa", "Camiseta", "Bermuda", "Calça", "Jaqueta"]),
        ("Moda Íntima", 12, 19, 129, ["Sutiã", "Calcinha", "Pijama", "Cueca"]),
        ("Calçados", 18, 79, 399, ["Tênis", "Sandália", "Bota", "Sapatilha"]),
        ("Moda Praia", 10, 39, 199, ["Biquíni", "Maiô", "Saída de praia", "Sunga"]),
        ("Plus Size", 10, 59, 299, ["Vestido", "Blusa", "Calça"]),
    ],
    "Beleza & Cosméticos": [
        ("Skincare", 30, 29, 249, ["Sérum", "Hidratante", "Protetor solar", "Tônico"]),
        ("Maquiagem", 28, 19, 189, ["Base", "Batom", "Máscara de cílios", "Paleta"]),
        ("Cabelos", 22, 19, 159, ["Shampoo", "Condicionador", "Máscara capilar", "Óleo capilar"]),
        ("Perfumaria", 20, 59, 499, ["Perfume", "Body splash", "Colônia"]),
    ],
    "Casa & Decoração": [
        ("Decoração", 30, 29, 399, ["Vaso", "Quadro", "Luminária", "Almofada"]),
        ("Cama Mesa Banho", 30, 39, 349, ["Jogo de lençol", "Toalha", "Edredom", "Toalha de mesa"]),
        ("Utilidades", 25, 15, 199, ["Organizador", "Pote", "Panela", "Jogo de copos"]),
        ("Móveis", 15, 199, 1999, ["Poltrona", "Mesa lateral", "Estante", "Banqueta"]),
    ],
    "Eletrônicos": [
        ("Celulares", 30, 799, 5999, ["Smartphone"]),
        ("Acessórios para Celular", 25, 19, 199, ["Capa", "Carregador", "Película", "Fone com fio"]),
        ("Informática", 20, 99, 4999, ["Notebook", "Mouse", "Teclado", "Monitor"]),
        ("Áudio & TV", 15, 99, 3999, ["Caixa de som", "Fone Bluetooth", "Smart TV", "Soundbar"]),
        ("Games", 10, 49, 3999, ["Controle", "Jogo", "Console", "Headset"]),
    ],
    "Esporte & Fitness": [
        ("Roupas Fitness", 35, 39, 199, ["Legging", "Top", "Shorts", "Camiseta dry"]),
        ("Suplementos", 30, 49, 249, ["Whey", "Creatina", "Pré-treino", "Barra proteica"]),
        ("Equipamentos", 20, 29, 899, ["Halter", "Tapete de yoga", "Elástico", "Corda"]),
        ("Tênis Esportivo", 15, 149, 799, ["Tênis de corrida", "Tênis de treino"]),
    ],
    "Pet Shop": [
        ("Ração", 45, 59, 399, ["Ração cães adultos", "Ração gatos", "Ração filhotes"]),
        ("Petiscos", 20, 9, 59, ["Bifinho", "Sachê", "Osso"]),
        ("Higiene Pet", 15, 15, 89, ["Areia sanitária", "Tapete higiênico", "Shampoo pet"]),
        ("Acessórios Pet", 20, 19, 299, ["Coleira", "Cama pet", "Comedouro", "Brinquedo pet"]),
    ],
    "Alimentos & Bebidas": [
        ("Mercearia", 35, 9, 89, ["Café especial", "Azeite", "Granola", "Mel"]),
        ("Bebidas", 25, 15, 299, ["Vinho", "Cerveja artesanal", "Kombucha", "Chá"]),
        ("Naturais", 25, 9, 99, ["Mix de castanhas", "Pasta de amendoim", "Chips de legumes"]),
        ("Doces", 15, 9, 79, ["Chocolate", "Brigadeiro gourmet", "Biscoito"]),
    ],
    "Acessórios": [
        ("Bolsas", 30, 79, 599, ["Bolsa", "Mochila", "Carteira", "Necessaire"]),
        ("Bijuterias", 30, 19, 149, ["Brinco", "Colar", "Pulseira", "Anel"]),
        ("Relógios", 15, 99, 999, ["Relógio"]),
        ("Óculos", 25, 59, 499, ["Óculos de sol", "Armação"]),
    ],
    "Infantil": [
        ("Roupas Infantis", 40, 29, 159, ["Body", "Conjunto infantil", "Vestido infantil", "Pijama infantil"]),
        ("Brinquedos", 35, 19, 399, ["Boneca", "Blocos de montar", "Pelúcia", "Quebra-cabeça"]),
        ("Bebê", 25, 29, 499, ["Mamadeira", "Fralda", "Carrinho de bebê", "Mordedor"]),
    ],
    "Saúde & Bem-estar": [
        ("Vitaminas", 40, 29, 149, ["Multivitamínico", "Ômega 3", "Vitamina D", "Colágeno"]),
        ("Aromaterapia", 30, 19, 199, ["Óleo essencial", "Difusor", "Vela aromática"]),
        ("Cuidados Pessoais", 30, 15, 129, ["Escova", "Massageador", "Kit cuidados"]),
    ],
}

MARCAS = {
    "Moda": ["Aurora", "Linho & Cia", "Maré Alta", "Vértice", "Bossa", "Nativa", "Urbe", "Clara Luz"],
    "Beleza & Cosméticos": ["Botânica", "Pura Pele", "Lumina", "Essenza", "Flor do Cerrado", "Vitta Bella"],
    "Casa & Decoração": ["Casa Raiz", "Ninho", "Trama", "Alvorada Home", "Bem Morar", "Oca"],
    "Eletrônicos": ["Voltix", "Nexo", "Pulsar", "Orbita", "Kraft Tech", "Sintonia"],
    "Esporte & Fitness": ["Fôlego", "Atleta+", "Corre", "Força Natural", "Ritmo", "Endurance"],
    "Pet Shop": ["Patas", "Focinho Feliz", "PetVida", "Amigo Fiel", "Miau & Au", "NutriPet"],
    "Alimentos & Bebidas": ["Terra Boa", "Sítio Verde", "Grão Nobre", "Colheita", "Sabor da Serra"],
    "Acessórios": ["Prata Fina", "Brilho", "Andarilha", "Horizonte", "Zênite", "Ponto Ouro"],
    "Infantil": ["Pequeno Mundo", "Brincar", "Ciranda", "Mini Moda", "Cantiga"],
    "Saúde & Bem-estar": ["Equilíbrio", "Vida Plena", "Bem Estar Já", "Essência Natural", "Calma"],
}

ADJETIVOS = ["Clássico", "Premium", "Essencial", "Plus", "Pro", "Básico", "Deluxe", "Eco", "Max", "Slim", "Soft", "Original"]

PREFIXOS_LOJA = {
    "Moda": ["Ateliê", "Boutique", "Closet", "Estilo", "Vitrine", "Moda"],
    "Beleza & Cosméticos": ["Bella", "Espaço", "Studio", "Beauty", "Empório"],
    "Casa & Decoração": ["Casa", "Lar", "Empório", "Cantinho", "Oficina"],
    "Eletrônicos": ["Tech", "Digital", "Eletro", "Conecta", "Mega"],
    "Esporte & Fitness": ["Fit", "Sport", "Treino", "Arena", "Corpo"],
    "Pet Shop": ["Pet", "Mundo Pet", "Bicho", "Patinhas", "Clube Pet"],
    "Alimentos & Bebidas": ["Empório", "Mercadinho", "Adega", "Sabores", "Quitanda"],
    "Acessórios": ["Bijoux", "Acessórios", "Charme", "Detalhe", "Jóia"],
    "Infantil": ["Kids", "Pequenos", "Mundo Kids", "Baby", "Turminha"],
    "Saúde & Bem-estar": ["Natural", "Vida", "Bem", "Saúde", "Zen"],
}
NOMES_LOJA = ["Aurora", "Bella", "Lumi", "Raiz", "Brisa", "Flor de Lis", "Maré", "Sol", "Lua", "Jasmim", "Ipê",
              "Girassol", "Serena", "Dona Rosa", "do Bairro", "da Vila", "Central", "Paulista", "Carioca",
              "Mineira", "Gaúcha", "Nordeste", "Bahia", "Primavera", "Oásis", "Cristal", "Esperança", "Vitória",
              "Tropical", "Cerrado", "Amazônia", "Pampa", "Pantanal", "Litoral", "Serra", "Horizonte"]

# Distribuição de UF das lojas e das pessoas compradoras
UF_LOJAS = [("SP", 38), ("MG", 11), ("RJ", 10), ("PR", 7), ("RS", 7), ("SC", 6), ("BA", 4), ("PE", 3), ("GO", 3),
            ("DF", 2), ("CE", 2), ("ES", 2), ("PA", 1), ("AM", 0.6), ("MA", 0.5), ("PB", 0.6), ("RN", 0.5),
            ("AL", 0.4), ("PI", 0.3), ("SE", 0.3), ("MT", 0.6), ("MS", 0.6), ("TO", 0.2), ("RO", 0.2),
            ("AC", 0.1), ("AP", 0.1), ("RR", 0.1)]
UF_PESSOAS = [("SP", 22), ("MG", 10), ("RJ", 8.5), ("BA", 7), ("PR", 5.5), ("RS", 5.5), ("PE", 4.6), ("CE", 4.4),
              ("PA", 4), ("SC", 3.6), ("GO", 3.4), ("MA", 3.3), ("AM", 2), ("ES", 2), ("PB", 2), ("RN", 1.7),
              ("MT", 1.7), ("AL", 1.6), ("PI", 1.6), ("DF", 1.5), ("MS", 1.4), ("SE", 1.1), ("RO", 0.8),
              ("TO", 0.7), ("AC", 0.4), ("AP", 0.4), ("RR", 0.3)]

# uf -> (regiao, ddd, cep_min (2 dígitos), cep_max, [cidades])
UFS = {
    "SP": ("Sudeste", 11, 1, 19, ["São Paulo", "Campinas", "Santos", "Ribeirão Preto", "Sorocaba", "São José dos Campos", "Guarulhos"]),
    "RJ": ("Sudeste", 21, 20, 28, ["Rio de Janeiro", "Niterói", "Petrópolis", "Duque de Caxias"]),
    "ES": ("Sudeste", 27, 29, 29, ["Vitória", "Vila Velha"]),
    "MG": ("Sudeste", 31, 30, 39, ["Belo Horizonte", "Uberlândia", "Juiz de Fora", "Contagem"]),
    "BA": ("Nordeste", 71, 40, 48, ["Salvador", "Feira de Santana", "Vitória da Conquista"]),
    "SE": ("Nordeste", 79, 49, 49, ["Aracaju"]),
    "PE": ("Nordeste", 81, 50, 56, ["Recife", "Olinda", "Caruaru"]),
    "AL": ("Nordeste", 82, 57, 57, ["Maceió"]),
    "PB": ("Nordeste", 83, 58, 58, ["João Pessoa", "Campina Grande"]),
    "RN": ("Nordeste", 84, 59, 59, ["Natal"]),
    "CE": ("Nordeste", 85, 60, 63, ["Fortaleza", "Juazeiro do Norte"]),
    "PI": ("Nordeste", 86, 64, 64, ["Teresina"]),
    "MA": ("Nordeste", 98, 65, 65, ["São Luís"]),
    "PA": ("Norte", 91, 66, 68, ["Belém", "Santarém"]),
    "AP": ("Norte", 96, 68, 68, ["Macapá"]),
    "AM": ("Norte", 92, 69, 69, ["Manaus"]),
    "RR": ("Norte", 95, 69, 69, ["Boa Vista"]),
    "AC": ("Norte", 68, 69, 69, ["Rio Branco"]),
    "RO": ("Norte", 69, 76, 76, ["Porto Velho"]),
    "TO": ("Norte", 63, 77, 77, ["Palmas"]),
    "DF": ("Centro-Oeste", 61, 70, 73, ["Brasília"]),
    "GO": ("Centro-Oeste", 62, 74, 76, ["Goiânia", "Anápolis"]),
    "MT": ("Centro-Oeste", 65, 78, 78, ["Cuiabá"]),
    "MS": ("Centro-Oeste", 67, 79, 79, ["Campo Grande"]),
    "PR": ("Sul", 41, 80, 87, ["Curitiba", "Londrina", "Maringá"]),
    "SC": ("Sul", 48, 88, 89, ["Florianópolis", "Joinville", "Blumenau"]),
    "RS": ("Sul", 51, 90, 99, ["Porto Alegre", "Caxias do Sul", "Pelotas"]),
}

PRIMEIROS_NOMES = ["Ana", "Maria", "Julia", "Beatriz", "Larissa", "Camila", "Fernanda", "Gabriela", "Mariana",
                   "Amanda", "Letícia", "Bruna", "Patrícia", "Aline", "Juliana", "Renata", "Carla", "Vanessa",
                   "Isabela", "Sofia", "Helena", "Valentina", "Alice", "Laura", "Manuela", "Luana", "Débora",
                   "João", "Pedro", "Lucas", "Gabriel", "Rafael", "Gustavo", "Felipe", "Bruno", "Rodrigo",
                   "Thiago", "Diego", "Matheus", "Leonardo", "Eduardo", "Marcelo", "André", "Carlos", "Paulo",
                   "Ricardo", "Fernando", "Vinícius", "Daniel", "Henrique", "Arthur", "Miguel", "Davi", "Caio",
                   "Igor", "Renan", "Otávio", "Murilo", "Samuel", "Enzo"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima",
              "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes",
              "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques",
              "Machado", "Mendes", "Freitas", "Cardoso", "Ramos", "Gonçalves", "Santana", "Teixeira", "Araújo",
              "Pinto", "Correia", "Moraes", "Batista"]
PROVEDORES_EMAIL = [("gmail.com", 50), ("hotmail.com", 15), ("outlook.com", 12), ("yahoo.com.br", 8),
                    ("icloud.com", 7), ("uol.com.br", 4), ("bol.com.br", 4)]

PLANOS = ["Inicial", "Básico", "Essencial", "Profissional", "Avançado"]
PRECO_PLANO = {"Inicial": 49.0, "Básico": 99.0, "Essencial": 199.0, "Profissional": 399.0, "Avançado": 899.0}
PRECO_INICIAL_REAJUSTADO = 69.0
CHURN_MENSAL = {"Inicial": 0.020, "Básico": 0.012, "Essencial": 0.008, "Profissional": 0.005, "Avançado": 0.003}

CANAIS_AQUISICAO = [("Busca orgânica", 22), ("Anúncios Meta", 18), ("Anúncios Google", 14), ("Instagram", 16),
                    ("WhatsApp", 10), ("Marketplace", 12), ("Indicação", 8)]

TRANSPORTADORAS = [("Postal Brasil", 40), ("Rota Express", 20), ("Leva Já", 15), ("Entrega Certa", 15),
                   ("Rápido Sul", 10)]

CUPONS = ["BEMVINDO10", "FRETEGRATIS", "VOLTA15", "BLACK20", "PRIMEIRACOMPRA", "CLIENTEVIP", "NATAL10", "INSTA5"]
