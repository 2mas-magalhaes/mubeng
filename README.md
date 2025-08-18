// --- Importações ---
const fetch = (...args) => import('node-fetch').then(({ default: f }) => f(...args));
const { HttpsProxyAgent } = require('https-proxy-agent');
const cheerio = require('cheerio');

// --- Objeto de Exportação ---
const fetcher = {
  fetchPage: null,
  fetchSearchPage: null,
  fetchAllListingsPages: null,
  ready: Promise.resolve() // Fica pronto imediatamente, sem inicialização complexa
};

// --- Função Principal de Inicialização ---
async function initialize() {
  const pLimit = (await import('p-limit')).default;

  // --- LÓGICA DE SCRAPING DA STEAM ---
  
  // O único proxy de que o nosso script precisa de saber é o do nosso servidor mubeng
  const MUBENG_PROXY_URL = 'http://localhost:8089';
  const agent = new HttpsProxyAgent(MUBENG_PROXY_URL);

  const BASE_LISTING_URL = 'https://steamcommunity.com/market/listings/730';
  const BASE_SEARCH_URL = 'https://steamcommunity.com/market/search/render/';

  // Não precisamos de ignorar certificados aqui porque o mubeng trata da ligação
  // e o nosso script só fala com o mubeng em HTTP simples.

  async function fetchTotalPages(itemName) {
      const encodedItem = encodeURIComponent(itemName);
      const steamUrl = `${BASE_LISTING_URL}/${encodedItem}`;
      console.log(`ℹ️  A obter contagem de páginas para [${itemName}] via mubeng...`);
      try {
          // Adicionado timeout de 20 segundos para esta chamada crítica
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 20000);
          const response = await fetch(steamUrl, { agent, signal: controller.signal, headers: { 'User-Agent': 'Mozilla/5.0' } });
          clearTimeout(timeoutId);

          if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
          const html = await response.text();
          const $ = cheerio.load(html);
          const lastPageLink = $('.market_paging_pagelink').last();
          return lastPageLink.length > 0 ? parseInt(lastPageLink.text().trim(), 10) : 1;
      } catch (error) {
          console.error(`❌ Falha ao obter contagem de páginas para [${itemName}]: ${error.message}`);
          return null;
      }
  }

  async function fetchPage(itemName, start, count) {
    const encodedItem = encodeURIComponent(itemName);
    const steamUrl = `${BASE_LISTING_URL}/${encodedItem}/render/?start=${start}&count=${count}&country=PT&language=portuguese&currency=3`;
    const pageNumber = start / count + 1;
    console.log(`➡️  A buscar [${itemName}] (página ${pageNumber}) via mubeng...`);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 20000);
      const response = await fetch(steamUrl, { agent, signal: controller.signal, headers: { 'User-Agent': 'Mozilla/5.0' } });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
      const data = await response.json();
      console.log(`✔️  Sucesso para [${itemName}] (página ${pageNumber})`);
      return data;
    } catch (error) {
      console.error(`❌  Falha para [${itemName}] (página ${pageNumber}): ${error.message}`);
      return null;
    }
  }
  
  async function fetchAllListingsPages(itemName) {
    console.log(`\n🚀 A iniciar busca para o item: ${itemName}`);
    const totalPages = await fetchTotalPages(itemName);
    if (!totalPages) {
      console.error(`Falha crítica ao obter número de páginas para ${itemName}. A cancelar.`);
      return null;
    }
    console.log(`ℹ️  Item [${itemName}] tem um total de ${totalPages} páginas.`);
    
    // Podemos aumentar o paralelismo porque o mubeng é muito rápido e robusto
    const limit = pLimit(10);
    const tasks = [];
    for (let i = 0; i < totalPages; i++) {
      tasks.push(limit(() => fetchPage(itemName, i * 100, 100)));
    }

    console.log(`⏳ A executar ${tasks.length} buscas em paralelo...`);
    const results = await Promise.all(tasks);
    const successfulPages = results.filter(page => page);
    
    console.log(`🏁 Processo concluído para [${itemName}]: ${successfulPages.length} de ${totalPages} páginas obtidas.`);
    return successfulPages;
  }
  
  async function fetchSearchPage(query, start = 0, count = 100) {
    const steamUrl = `${BASE_SEARCH_URL}?query=${encodeURIComponent(query)}&appid=730&start=${start}&count=${count}&country=PT&language=portuguese&currency=3`;
    try {
      const response = await fetch(steamUrl, { agent });
      if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`❌ Falha na pesquisa: ${error.message}`);
      return null;
    }
  }
  
  fetcher.fetchPage = fetchPage;
  fetcher.fetchSearchPage = fetchSearchPage;
  fetcher.fetchAllListingsPages = fetchAllListingsPages;
  
  console.log("Módulo de fetch inicializado e pronto para usar o mubeng em localhost:8089.");
}

initialize();

module.exports = fetcher;