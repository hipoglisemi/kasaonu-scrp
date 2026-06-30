
        const initPagniation= function(dataSource)
        {
            Feux.Pagination.init({
                    dataSource: dataSource,
                    pagePerItem: 6,
                    step: 3,
                    showPrevious: true,
                    showNext: true,
                    containerId: pagination,
                    paginatorId: paginator,
                    templateId: pageComponent,
                    nextButtonImg: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">\
                                    <g fill="none"fill-rule="evenodd" >\
                                <g>\
                                    <g transform="translate(-343 -610) translate(343 610)">\
                                        <circle cx="20" cy="20" r="20" fill="#FFF" />\
                                        <path stroke="#FF5C33" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 13L25 20 18 27" />\
                                    </g>\
                                </g>\
                            </g>\
                            </svg>',
                    prevButtonImg: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">\
                                    <g fill="none"fill-rule="evenodd">\
                                        <g>\
                                            <g>\
                                                <g transform="translate(-282 -610) translate(282 610) matrix(-1 0 0 1 40 0)">\
                                                    <circle cx="20" cy="20" r="20" fill="#FFF" />\
                                                    <path stroke="#FF5C33" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 13L25 20 18 27" />\
                                                </g>\
                                            </g>\
                                        </g>\
                                    </g>\
                                </svg>',
                    nextButtonImgDisabled: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">\
                                    <g fill="none"fill-rule="evenodd" >\
                                <g>\
                                    <g transform="translate(-343 -610) translate(343 610)">\
                                        <circle cx="20" cy="20" r="20" fill="#FFF" />\
                                        <path stroke="#d8d8d8" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 13L25 20 18 27" />\
                                    </g>\
                                </g>\
                            </g>\
                            </svg>',
                    prevButtonImgDisabled: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">\
                                    <g fill="none"fill-rule="evenodd">\
                                        <g>\
                                            <g>\
                                                <g transform="translate(-282 -610) translate(282 610) matrix(-1 0 0 1 40 0)">\
                                                    <circle cx="20" cy="20" r="20" fill="#FFF" />\
                                                    <path stroke="#d8d8d8" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 13L25 20 18 27" />\
                                                </g>\
                                            </g>\
                                        </g>\
                                    </g>\
                                </svg>',

                });
        };

        initPagniation([{"pageUrl":"d-rda-pokus-troy-sanal-karta-1000-tlye-varan-indirim","title":"D&R’da Pokus Troy Sanal Kart’a 1.000 TL’ye varan indirim!","discount":"Anında 200 TL indirim!","bgImage":"/media/tqrlnl3e/d-r_384x180_12-06_2026_mor.jpg","cokYakinda":false,"kampanyaKategorisi":"#Alışveriş"},{"pageUrl":"pokusla-tek-seferde-yapacagin-750-tl-ve-uzeri-restoran-harcamalarina-75-tl-hediye","title":"Pokus’la tek seferde yapacağın 750 TL ve üzeri restoran harcamalarına 75 TL hediye!","discount":"75 TL Hediye!","bgImage":"/media/dwjhm44b/restoran_384x180_12-06_2026_mor.jpg","cokYakinda":false,"kampanyaKategorisi":"#Yeme/İçme"},{"pageUrl":"pokus-troy-sanal-kartla-idefixte-her-1000-tllik-alisverise-200-tl-indirim","title":"Pokus Troy Sanal Kart’la idefix’te her 1.000 TL’lik alışverişe 200 TL indirim!","discount":"Anında 200 TL indirim!","bgImage":"/media/fdgcf2xa/idefix_384x180_10-06_2026_yes-ºil.jpg","cokYakinda":false,"kampanyaKategorisi":"#Alışveriş"},{"pageUrl":"lc-waikikide-pokus-troy-sanal-kartinla-3000-tlye-300-tl-indirim-firsati","title":"LC Waikiki’de POKUS TROY Sanal Kartı’nla 3.000 TL’ye 300 TL İndirim Fırsatı!","discount":"Anında 300 TL indirim!","bgImage":"/media/1gobnv12/lc-waikiki_384x180_05-06_2026_yes-ºil.jpg","cokYakinda":false,"kampanyaKategorisi":"#Alışveriş"},{"pageUrl":"ekspres-hesapin-avantajli-dunyasiyla-tanismanin-tam-zamani","title":"Ekspres Hesap’ın avantajlı dünyasıyla tanışmanın tam zamanı! ","discount":"2 GB Hediye!","bgImage":"/media/niqdl1ar/ekspres-hesap_384x180_05-05_2026_mor.jpg","cokYakinda":false,"kampanyaKategorisi":"#İnternet"},{"pageUrl":"cicek-gibi-indirim-ciceksepetinde","title":"Çiçek gibi indirim Çiçeksepeti’nde!","discount":"Anında %15 indirim!","bgImage":"/media/l01dz3yy/ciceksepeti-384x180-18-06-2025.png","cokYakinda":false,"kampanyaKategorisi":"#Alışveriş"},{"pageUrl":"mistikist-te-pokus-kart-in-ile-harca-aninda-15-indirim-kazan","title":"Mistikist’te Pokus Kart’ın ile harca, anında %15 indirim kazan!","discount":"1.050 TL’ye varan anında indirim!","bgImage":"/media/s5rbrzgz/mistikist-384x180-28-11-2024.png","cokYakinda":false,"kampanyaKategorisi":"#Eğlence"}]);

        const btnSearch= document.querySelector("#search-button");

        const searchFn = function(){
            const query= document.querySelector("#search-box").value;
            const rightContentEl= document.querySelector(".right-content");

            if(!rightContentEl.classList.contains("active")) return false;
            if(!query) return false;

            let isActive = 1;
            let jsonInput = JSON.stringify({ isActive: isActive, query: query});
            let scrollYPos;
            $.ajax({
                type: 'POST',
                url: '/umbraco/surface/CustomSearch/SearchCampaigns',
                contentType: 'application/json',
                data: jsonInput,
                success: function (result) {
                    const searchResults = JSON.parse(JSON.stringify(result.Result));

                    if(!searchResults.length)
                    {
                        let template= `
                            <div class="not-found">
                                <div class="not-found-icon">
                                    <div class="exclamation">
                                    </div>
                                </div>
                            <div class="text">
                                Aradağınız içerik bulunamamıştır.
                            </div>
                        </div>`;
                        document.querySelector("#pagination").innerHTML=template;
                        document.querySelector("#paginator").style.display="none";

                        return false;
                    }
                    document.querySelector("#paginator").style.display = "flex";
                    initPagniation(searchResults);
                    if (searchResults.length > 6) document.querySelector("#paginator").style.opacity ="1";
                    document.querySelector('.right-content').classList.remove('active');
                    document.querySelector('#search-box').value = "";
                    document.querySelector('.left-content').style.zIndex = "2";
                },
                error: function () {
                    alert('Failed to receive the Data');
                    console.log('Failed ');
                }
            })
        }
        window.addEventListener('keypress', function(e)
        {
            if(e.charCode ===13) searchFn();
        });

        btnSearch.addEventListener('click', searchFn);

    