const MODES={
    easy:{reward:100},
    medium:{reward:250},
    hard:{reward:500}
};

function touch(){
    return (
        navigator.maxTouchPoints>0
        || window.matchMedia(
            "(pointer: coarse)"
        ).matches
    );
}

export async function mountThornfield({
    app,
    api,
    user,
    back
}){
    let state=null;
    let flagMode=false;
    let startedAt=0;
    let frozen=0;
    let busy=false;
    let alive=true;

    function time(){
        if(!state)
            return "0:00";

        let seconds=frozen;

        if(
            !state.done
            && startedAt
        ){
            seconds=(
                Date.now()
                -startedAt
            )/1000;
        }

        seconds=Math.max(
            0,
            Math.floor(seconds)
        );

        return (
            `${Math.floor(seconds/60)}:`
            +String(seconds%60).padStart(2,"0")
        );
    }

    function clock(){
        if(!state)
            return;

        frozen=state.elapsed||0;
        startedAt=(
            state.elapsed
            ? Date.now()-state.elapsed*1000
            : 0
        );
    }

    function shell(remaining=3){
        if(!alive)
            return;

        const done=Math.max(
            0,
            Math.min(3,3-remaining)
        );

        app.innerHTML=`
            <main class="thornfield-main">
                <header>
                    <div>
                        <h1>🪡 thornfield</h1>
                        <p class="sub">
                            (welcome to minesweeper)
                        </p>
                    </div>

                    <div class="thornfield-head-right">
                        <span class="player">
                            ${user?.name||""}
                        </span>
                        <button
                            type="button"
                            id="parlor"
                            class="icon"
                            aria-label="parlor"
                        >🎴</button>
                    </div>
                </header>

                <nav id="modes" class="modes"></nav>

                <section id="panel" class="panel">
                    <div class="welcome">
                        <div class="thorn">✦</div>
                        <h2>pick a patch</h2>
                        <p>${done} / 3 rewards claimed 🪡</p>
                    </div>
                </section>
            </main>
        `;

        document
            .querySelector("#parlor")
            .addEventListener(
                "click",
                back
            );

        const modes=
            document.querySelector("#modes");

        for(
            const [name,data]
            of Object.entries(MODES)
        ){
            const button=
                document.createElement("button");

            button.type="button";
            button.className="mode";
            button.dataset.mode=name;
            button.innerHTML=`
                <strong>${name}</strong>
                <span>${data.reward.toLocaleString()} roses 🌹</span>
            `;

            button.addEventListener(
                "click",
                ()=>start(name)
            );

            modes.appendChild(button);
        }
    }

    function fit(){
        if(!state||!alive)
            return;

        const wrap=
            document.querySelector("#boardwrap");
        const board=
            document.querySelector("#board");

        if(!wrap||!board)
            return;

        const coarse=touch();
        wrap.classList.toggle("touchboard",coarse);

        const width=Math.max(
            250,
            wrap.clientWidth-8
        );

        const rect=wrap.getBoundingClientRect();
        const height=Math.max(
            250,
            window.innerHeight-rect.top-22
        );

        let size;

        if(coarse){
            if(window.innerWidth>=700){
                size=Math.max(
                    24,
                    Math.min(
                        42,
                        Math.floor(width/state.w),
                        Math.floor(height/state.h)
                    )
                );
            }else{
                const minimum=(
                    state.w<=10
                    ? 28
                    : state.w<=18
                        ? 26
                        : 24
                );

                size=Math.min(
                    36,
                    Math.max(
                        minimum,
                        Math.floor(width/state.w)
                    )
                );
            }

            wrap.style.maxHeight=`${height}px`;
        }else{
            size=Math.max(
                18,
                Math.min(
                    42,
                    Math.floor(width/state.w),
                    Math.floor(height/state.h)
                )
            );

            wrap.style.maxHeight=`${height}px`;
        }

        board.style.setProperty(
            "--cell",
            `${size}px`
        );

        requestAnimationFrame(()=>{
            if(!alive)
                return;

            wrap.classList.toggle(
                "centered",
                board.scrollWidth<=wrap.clientWidth
            );
        });
    }

    function top(){
        return `
            <div class="topbar">
                <div class="stats">
                    <span>🪡 <b>${state.mines-state.flags}</b></span>
                    <span>⏱ <b id="timer">${time()}</b></span>
                    <span><b>${state.rewards_remaining} / 3</b> 🪡</span>
                </div>

                <div class="tools">
                    <button
                        type="button"
                        id="flag"
                        class="icon ${flagMode?"active":""}"
                        aria-label="flag mode"
                    >🚩</button>
                    <button
                        type="button"
                        id="again"
                        class="icon"
                        aria-label="new board"
                    >↻</button>
                    <button
                        type="button"
                        id="newyes"
                        class="icon"
                        aria-label="confirm new board"
                        hidden
                    >✅</button>
                    <button
                        type="button"
                        id="newno"
                        class="icon"
                        aria-label="cancel new board"
                        hidden
                    >❌</button>
                </div>
            </div>
        `;
    }

    function cls(value){
        if(value==="c") return "covered";
        if(value==="f") return "flagged";
        if(value==="m") return "mine";
        if(value==="x") return "hit";
        if(value==="w") return "wrong";
        return `open n${value}`;
    }

    function text(value){
        if(value==="c") return "";
        if(value==="f") return "🚩";
        if(value==="m") return "✦";
        if(value==="x") return "✹";
        if(value==="w") return "×";
        if(value==="0") return "";
        return value;
    }

    function label(value,x,y){
        if(value==="c") return `covered square ${x+1}, ${y+1}`;
        if(value==="f") return `flagged square ${x+1}, ${y+1}`;
        if(value==="m") return `thorn ${x+1}, ${y+1}`;
        if(value==="x") return `hit thorn ${x+1}, ${y+1}`;
        if(value==="w") return `wrong flag ${x+1}, ${y+1}`;
        if(value==="0") return `empty square ${x+1}, ${y+1}`;
        return `${value} at ${x+1}, ${y+1}`;
    }

    async function move(path,x,y){
        if(busy||!alive)
            return;

        busy=true;

        try{
            state=await api(
                path,
                "POST",
                {x,y}
            );

            clock();
            render(false);
        }catch(error){
            fail(error);
        }finally{
            busy=false;
        }
    }

    function cell(value,x,y){
        const button=
            document.createElement("button");

        button.type="button";
        button.className=`cell ${cls(value)}`;
        button.textContent=text(value);
        button.setAttribute(
            "aria-label",
            label(value,x,y)
        );

        let timer=null;
        let held=false;
        let moved=false;
        let startX=0;
        let startY=0;

        const clear=()=>{
            if(timer!==null){
                clearTimeout(timer);
                timer=null;
            }
        };

        button.addEventListener(
            "contextmenu",
            event=>{
                event.preventDefault();

                if(
                    !busy
                    && (value==="c"||value==="f")
                ){
                    move("/game/flag",x,y);
                }
            }
        );

        button.addEventListener(
            "pointerdown",
            event=>{
                if(event.pointerType==="mouse")
                    return;

                held=false;
                moved=false;
                startX=event.clientX;
                startY=event.clientY;

                timer=setTimeout(()=>{
                    if(moved||busy)
                        return;

                    held=true;
                    if(value==="c"||value==="f"){
                        move("/game/flag",x,y);
                    }
                },450);
            }
        );

        button.addEventListener(
            "pointermove",
            event=>{
                if(timer===null)
                    return;

                if(
                    Math.hypot(
                        event.clientX-startX,
                        event.clientY-startY
                    )>10
                ){
                    moved=true;
                    clear();
                }
            }
        );

        button.addEventListener("pointerup",clear);
        button.addEventListener("pointercancel",clear);
        button.addEventListener(
            "pointerleave",
            ()=>{
                if(moved)
                    clear();
            }
        );

        button.addEventListener(
            "click",
            async()=>{
                if(held||moved||busy){
                    held=false;
                    moved=false;
                    return;
                }

                if(state.done)
                    return;

                if(flagMode){
                    if(value==="c"||value==="f"){
                        await move("/game/flag",x,y);
                    }
                    return;
                }

                if(value!=="f"){
                    await move("/game/reveal",x,y);
                }
            }
        );

        return button;
    }

    function render(resetScroll=false){
        if(!state||!alive)
            return;

        const oldWrap=
            document.querySelector("#boardwrap");

        const scroll={
            left:oldWrap?oldWrap.scrollLeft:0,
            top:oldWrap?oldWrap.scrollTop:0
        };

        document
            .querySelectorAll(".mode")
            .forEach(button=>{
                button.classList.toggle(
                    "selected",
                    button.dataset.mode===state.mode
                );
            });

        const panel=
            document.querySelector("#panel");

        if(!panel)
            return;

        panel.innerHTML=`
            ${top()}
            <div id="boardwrap" class="boardwrap">
                <div id="board" class="board"></div>
            </div>
            <div id="note" class="note" aria-live="polite"></div>
        `;

        const board=
            document.querySelector("#board");

        board.style.gridTemplateColumns=
            `repeat(${state.w},var(--cell))`;

        state.grid.forEach((row,y)=>{
            row.forEach((value,x)=>{
                board.appendChild(
                    cell(value,x,y)
                );
            });
        });

        const note=
            document.querySelector("#note");

        if(state.note){
            note.textContent=state.note;
            note.classList.add(
                state.won?"win":"death"
            );
        }else if(state.rewards_remaining===0){
            note.textContent=
                "you're playing for fun now";
        }

        document
            .querySelector("#flag")
            .addEventListener("click",()=>{
                flagMode=!flagMode;
                render(false);
            });

        const again=
            document.querySelector("#again");

        const newyes=
            document.querySelector("#newyes");

        const newno=
            document.querySelector("#newno");

        again.addEventListener("click",()=>{
            again.hidden=true;
            newyes.hidden=false;
            newno.hidden=false;
        });

        newyes.addEventListener(
            "click",
            ()=>start(state.mode)
        );

        newno.addEventListener("click",()=>{
            newyes.hidden=true;
            newno.hidden=true;
            again.hidden=false;
        });

        fit();

        const wrap=
            document.querySelector("#boardwrap");

        if(wrap&&!resetScroll){
            wrap.scrollLeft=scroll.left;
            wrap.scrollTop=scroll.top;
        }
    }

    async function start(mode){
        if(busy||!alive)
            return;

        busy=true;

        try{
            flagMode=false;
            state=await api(
                "/game/new",
                "POST",
                {mode}
            );
            clock();
            render(true);
        }catch(error){
            fail(error);
        }finally{
            busy=false;
        }
    }

    function fail(error){
        if(!alive)
            return;

        app.innerHTML=`
            <main class="thornfield-main">
                <div class="error">
                    <h1>🪡 thornfield</h1>
                    <p>rosie stepped on her own thorn</p>
                    <code>${String(error.message||error)}</code>
                    <button type="button" id="parlor">🎴</button>
                </div>
            </main>
        `;

        document
            .querySelector("#parlor")
            .addEventListener("click",back);
    }

    const status=await api("/status");
    shell(status.rewards_remaining);

    const timer=setInterval(()=>{
        if(!alive)
            return;

        const el=document.querySelector("#timer");
        if(el&&state&&!state.done){
            el.textContent=time();
        }
    },250);

    const resize=()=>fit();
    const orient=()=>setTimeout(fit,120);

    window.addEventListener("resize",resize);
    window.addEventListener("orientationchange",orient);

    if(status.game){
        state=status.game;
        clock();
        render(true);
    }

    let closed=false;

    return ()=>{
        if(closed)
            return;

        closed=true;
        alive=false;
        clearInterval(timer);
        window.removeEventListener("resize",resize);
        window.removeEventListener("orientationchange",orient);
    };
}
