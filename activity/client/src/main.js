import {
    DiscordSDK
} from "@discord/embedded-app-sdk";

import "./style.css";
import {mountThornfield} from "./thornfield.js";

const CLIENT_ID=
    import.meta.env.VITE_DISCORD_CLIENT_ID;

const discordSdk=
    new DiscordSDK(
        CLIENT_ID
    );

const API="/.proxy/api";

let session=null;
let user=null;

let game=null;
let raf=null;
let busy=false;
let screen="parlor";
let cleanup=null;

const W=360000;
const H=560000;

const BX=90000;
const BW=26000;
const BH=20000;

const GRAVITY=380;
const FLAP=-6200;

const PW=62000;
const GAP_MIN=124000;
const GAP_RANGE=40001;
const SPEED=2600;
const SPACING=250000;
const FIRST=430000;

const CENTER_MIN=140000;
const CENTER_RANGE=280000;

const TOKEN_FIRST=3;
const TOKEN_EVERY=12;
const TOKEN_RADIUS=10000;
const TOKEN_EDGE=26000;
const TOKEN_BOOST=10;

const STEP=1000/60;

const app=
    document.querySelector(
        "#app"
    );

async function readjson(response){
    const raw=
        await response.text();

    if(!raw)
        return {};

    try{
        return JSON.parse(
            raw
        );

    }catch{
        const preview=
            raw
                .replace(
                    /\s+/g,
                    " "
                )
                .slice(
                    0,
                    120
                );

        throw new Error(
            `server ${response.status} ⊹ ${preview}`
        );
    }
}

async function api(
    path,
    method="GET",
    body=null
){
    const options={
        method,
        headers:{
            Authorization:
                `Bearer ${session}`
        }
    };

    if(body!==null){
        options.headers[
            "Content-Type"
        ]="application/json";

        options.body=
            JSON.stringify(
                body
            );
    }

    const response=
        await fetch(
            API+path,
            options
        );

    const data=
        await readjson(
            response
        );

    if(!response.ok){
        throw new Error(
            data.error
            || `request failed ${response.status}`
        );
    }

    return data;
}

function stop(){
    if(raf!==null){
        cancelAnimationFrame(
            raf
        );

        raf=null;
    }

    if(cleanup){
        cleanup();
        cleanup=null;
    }

    game=null;
}

async function thornfield(){
    stop();
    screen="thornfield";

    try{
        cleanup=await mountThornfield({
            app,
            api,
            user,
            back:parlor
        });
    }catch(error){
        fail(error);
    }
}

function parlor(){
    screen="parlor";
    stop();

    app.innerHTML=`
        <main class="parlor">
            <header>
                <h1>🕯️ parlor</h1>
            </header>

            <section class="games">
                <button
                    type="button"
                    id="thornfield"
                    class="game"
                >
                    <span class="icon">
                        🪡
                    </span>

                    <span class="copy">
                        <strong>
                            thornfield
                        </strong>

                        <small>
                            (welcome to minesweeper)
                        </small>
                    </span>
                </button>

                <button
                    type="button"
                    id="soaring"
                    class="game"
                >
                    <span class="icon">
                        🪽
                    </span>

                    <span class="copy">
                        <strong>
                            soaring
                        </strong>

                        <small>
                            (welcome to flappy bird)
                        </small>
                    </span>
                </button>
            </section>
        </main>
    `;

    document
        .querySelector(
            "#thornfield"
        )
        .addEventListener(
            "click",
            thornfield
        );

    document
        .querySelector(
            "#soaring"
        )
        .addEventListener(
            "click",
            soaring
        );
}

function center(index){
    while(
        game.centers.length<=index
    ){
        game.rng=(
            Math.imul(
                1664525,
                game.rng
            )
            +1013904223
        )>>>0;

        const state=
            game.rng;

        game.centers.push(
            CENTER_MIN
            +Math.floor(
                (
                    state
                    *CENTER_RANGE
                )
                /4294967296
            )
        );

        game.gaps.push(
            GAP_MIN
            +(
                (state>>>8)
                %GAP_RANGE
            )
        );
    }

    return game.centers[
        index
    ];
}

function opening(index){
    center(index);

    return game.gaps[
        index
    ];
}

function tokenY(index){
    if(
        index<TOKEN_FIRST
        || (index-TOKEN_FIRST)%TOKEN_EVERY
    ){
        return null;
    }

    const middle=
        center(index);

    const size=
        opening(index);

    const mixed=(
        (
            game.seed
            ^Math.imul(
                index+1,
                0x9E3779B9
            )
        )>>>0
    );

    return (
        (mixed&1)===0
        ? middle-size/2+TOKEN_EDGE
        : middle+size/2-TOKEN_EDGE
    );
}

function pipeX(
    index,
    tick=game.tick
){
    return (
        FIRST
        +index*SPACING
        -SPEED*tick
    );
}

function step(){
    if(
        !game
        || game.dead
    ){
        return;
    }

    if(game.pending){
        game.velocity=FLAP;

        game.flaps.push(
            game.tick
        );

        game.pending=false;
    }

    game.velocity+=
        GRAVITY;

    game.y+=
        game.velocity;

    const top=
        game.y-BH/2;

    const bottom=
        game.y+BH/2;

    if(
        top<=0
        || bottom>=H
    ){
        die();
        return;
    }

    const birdLeft=
        BX-BW/2;

    const birdRight=
        BX+BW/2;

    for(
        let index=game.nextPipe;
        index<game.nextPipe+4;
        index++
    ){
        const x=
            pipeX(index);

        const overlap=(
            birdRight>x
            && birdLeft<x+PW
        );

        if(overlap){
            const middle=
                center(index);

            const size=
                opening(index);

            if(
                top<middle-size/2
                || bottom>middle+size/2
            ){
                die();
                return;
            }
        }

        const ty=
            tokenY(index);

        if(
            ty===null
            || game.collected.has(index)
        ){
            continue;
        }

        const tx=
            x+PW/2;

        if(
            Math.abs(tx-BX)<=BW/2+TOKEN_RADIUS
            && Math.abs(ty-game.y)<=BH/2+TOKEN_RADIUS
        ){
            game.collected.add(index);
            game.boost=TOKEN_BOOST;
        }
    }

    while(
        pipeX(
            game.nextPipe
        )+PW<birdLeft
    ){
        game.score+=1;

        if(game.boost>0){
            game.credits+=2;
            game.boost-=1;
        }else{
            game.credits+=1;
        }

        game.nextPipe+=1;
    }

    game.tick+=1;
}

function bird(ctx){
    const x=
        BX/1000;

    const y=
        game.y/1000;

    ctx.save();

    ctx.translate(
        x,
        y
    );

    ctx.rotate(
        Math.max(
            -.35,
            Math.min(
                .65,
                game.velocity/12000
            )
        )
    );

    ctx.fillStyle=
        "#decac6";

    ctx.beginPath();

    ctx.ellipse(
        0,
        0,
        14,
        11,
        0,
        0,
        Math.PI*2
    );

    ctx.fill();

    ctx.fillStyle=
        "#671923";

    ctx.beginPath();

    ctx.ellipse(
        -5,
        3,
        8,
        5,
        -.4,
        0,
        Math.PI*2
    );

    ctx.fill();

    ctx.fillStyle=
        "#efb25b";

    ctx.beginPath();

    ctx.moveTo(
        11,
        -1
    );

    ctx.lineTo(
        22,
        3
    );

    ctx.lineTo(
        11,
        6
    );

    ctx.closePath();

    ctx.fill();

    ctx.fillStyle=
        "#231619";

    ctx.beginPath();

    ctx.arc(
        5,
        -4,
        2,
        0,
        Math.PI*2
    );

    ctx.fill();

    ctx.restore();
}

function draw(){
    if(
        !game
        || screen!=="soaring"
    ){
        return;
    }

    const canvas=
        document.querySelector(
            "#canvas"
        );

    if(!canvas)
        return;

    const ctx=
        canvas.getContext(
            "2d"
        );

    const gradient=
        ctx.createLinearGradient(
            0,
            0,
            0,
            560
        );

    gradient.addColorStop(
        0,
        "#220b0f"
    );

    gradient.addColorStop(
        1,
        "#0d090a"
    );

    ctx.fillStyle=
        gradient;

    ctx.fillRect(
        0,
        0,
        360,
        560
    );

    ctx.globalAlpha=.14;
    ctx.fillStyle="#ffffff";

    for(
        let i=0;
        i<9;
        i++
    ){
        const x=(
            (
                i*73
                -game.tick*.22
            )%430
            +430
        )%430-35;

        const y=
            35+(i*79)%470;

        ctx.beginPath();

        ctx.arc(
            x,
            y,
            2,
            0,
            Math.PI*2
        );

        ctx.fill();
    }

    ctx.globalAlpha=1;

    for(
        let index=game.nextPipe;
        index<game.nextPipe+4;
        index++
    ){
        const x=
            pipeX(index)/1000;

        if(
            x>430
            || x+62<-10
        ){
            continue;
        }

        const middle=
            center(index)/1000;

        const size=
            opening(index)/1000;

        const gapTop=
            middle-size/2;

        const gapBottom=
            middle+size/2;

        const pipe=
            ctx.createLinearGradient(
                x,
                0,
                x+62,
                0
            );

        pipe.addColorStop(
            0,
            "#260b10"
        );

        pipe.addColorStop(
            .5,
            "#55131c"
        );

        pipe.addColorStop(
            1,
            "#2d0d12"
        );

        ctx.fillStyle=
            pipe;

        ctx.fillRect(
            x,
            0,
            62,
            gapTop
        );

        ctx.fillRect(
            x,
            gapBottom,
            62,
            560-gapBottom
        );

        ctx.strokeStyle=
            "#762634";

        ctx.lineWidth=2;

        ctx.strokeRect(
            x,
            0,
            62,
            gapTop
        );

        ctx.strokeRect(
            x,
            gapBottom,
            62,
            560-gapBottom
        );
    }

    for(
        let index=game.nextPipe;
        index<game.nextPipe+4;
        index++
    ){
        const ty=tokenY(index);

        if(
            ty===null
            || game.collected.has(index)
        ){
            continue;
        }

        const tx=(
            pipeX(index)+PW/2
        )/1000;

        if(
            tx<-20
            || tx>380
        ){
            continue;
        }

        ctx.save();
        ctx.translate(
            tx,
            ty/1000
        );

        ctx.fillStyle="rgba(215,165,82,.18)";
        ctx.strokeStyle="#d7a552";
        ctx.lineWidth=2;
        ctx.beginPath();
        ctx.arc(0,0,14,0,Math.PI*2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle="#f2cf7a";
        ctx.font="800 22px system-ui";
        ctx.textAlign="center";
        ctx.textBaseline="middle";
        ctx.fillText("✦",0,1);
        ctx.restore();
    }

    bird(
        ctx
    );

    const score=
        document.querySelector(
            "#score"
        );

    const roses=
        document.querySelector(
            "#roses"
        );

    const multwrap=
        document.querySelector(
            "#multwrap"
        );

    const mult=
        document.querySelector(
            "#mult"
        );

    if(score){
        score.textContent=
            game.score;
    }

    if(roses){
        roses.textContent=
            Math.floor(
                game.credits/10
            );
    }

    if(multwrap&&mult){
        multwrap.hidden=
            game.dead
            || game.boost<1;
        mult.textContent=
            game.boost;
    }
}

function frame(timestamp){
    if(
        !game
        || game.dead
        || screen!=="soaring"
    ){
        return;
    }

    if(game.last===null){
        game.last=
            timestamp;
    }

    const delta=
        Math.min(
            100,
            timestamp-game.last
        );

    game.last=
        timestamp;

    game.acc+=
        delta;

    while(
        game.acc>=STEP
        && !game.dead
    ){
        step();

        game.acc-=
            STEP;
    }

    draw();

    if(
        game
        && !game.dead
    ){
        raf=
            requestAnimationFrame(
                frame
            );
    }
}

function flap(){
    if(
        screen!=="soaring"
        || !game
        || game.dead
    ){
        return;
    }

    game.pending=
        true;
}

async function start(){
    if(busy)
        return;

    busy=true;

    try{
        const run=
            await api(
                "/soaring/new",
                "POST"
            );

        if(raf!==null){
            cancelAnimationFrame(
                raf
            );

            raf=null;
        }

        game={
            runId:
                run.run_id,

            seed:
                Number(
                    run.seed
                )>>>0,

            rng:
                Number(
                    run.seed
                )>>>0,

            centers:[],

            gaps:[],

            tick:0,
            y:H/2,
            velocity:0,

            score:0,
            credits:0,
            boost:0,
            collected:new Set(),
            nextPipe:0,

            flaps:[],

            pending:true,
            dead:false,

            last:null,
            acc:0
        };

        const startButton=
            document.querySelector(
                "#start"
            );

        const again=
            document.querySelector(
                "#again"
            );

        const result=
            document.querySelector(
                "#result"
            );

        if(startButton){
            startButton.hidden=true;
        }

        if(again){
            again.hidden=true;
        }

        if(result){
            result.textContent="";
        }

        draw();

        raf=
            requestAnimationFrame(
                frame
            );

    }catch(error){
        resultError(
            error
        );

    }finally{
        busy=false;
    }
}

async function die(){
    if(
        !game
        || game.dead
    ){
        return;
    }

    game.dead=true;

    if(raf!==null){
        cancelAnimationFrame(
            raf
        );

        raf=null;
    }

    draw();

    const result=
        document.querySelector(
            "#result"
        );

    if(result){
        result.textContent="";
    }

    try{
        const data=
            await api(
                "/soaring/finish",
                "POST",
                {
                    run_id:
                        game.runId,

                    flaps:
                        game.flaps
                }
            );

        game.score=
            data.score;

        game.credits=
            data.reward*10;

        draw();

        if(result){
            result.textContent="";
        }

        const again=
            document.querySelector(
                "#again"
            );

        if(again){
            again.hidden=false;
        }

    }catch(error){
        if(result){
            result.textContent=
                `server said no ⊹ ${error.message}`;
        }
    }
}

function soaring(){
    screen="soaring";
    stop();

    app.innerHTML=`
        <main class="soaring-main">
            <header class="soaring-head">
                <div>
                    <h1>🪽 soaring</h1>

                    <p>
                        (welcome to flappy bird)
                    </p>
                </div>

                <button
                    type="button"
                    id="back"
                    class="home"
                >
                    🎴
                </button>
            </header>

            <section class="panel">
                <div class="stats">
                    <span>
                        score ⊹
                        <b id="score">0</b>
                    </span>

                    <span>
                        roses ⊹
                        <b id="roses">0</b>
                        🌹
                    </span>

                    <span
                        id="multwrap"
                        hidden
                    >
                        ✦ x2 ⊹
                        <b id="mult">0</b>
                    </span>
                </div>

                <canvas
                    id="canvas"
                    width="360"
                    height="560"
                    aria-label="soaring game"
                ></canvas>

                <div class="actions">
                    <button
                        type="button"
                        id="start"
                    >
                    ▶️
                </button>

                    <button
                        type="button"
                        id="again"
                        hidden
                    >
                    🔄
                </button>
                </div>

                <div
                    id="result"
                    class="result"
                    aria-live="polite"
                ></div>
            </section>
        </main>
    `;

    document
        .querySelector(
            "#back"
        )
        .addEventListener(
            "click",
            parlor
        );

    document
        .querySelector(
            "#start"
        )
        .addEventListener(
            "click",
            start
        );

    document
        .querySelector(
            "#again"
        )
        .addEventListener(
            "click",
            start
        );

    const canvas=
        document.querySelector(
            "#canvas"
        );

    canvas.addEventListener(
        "pointerdown",
        event=>{
            event.preventDefault();
            flap();
        }
    );

    const ctx=
        canvas.getContext(
            "2d"
        );

    ctx.fillStyle=
        "#190f12";

    ctx.fillRect(
        0,
        0,
        360,
        560
    );

    ctx.fillStyle=
        "#c5abad";

    ctx.font=
        "600 16px system-ui";

    ctx.textAlign=
        "center";

    
}

function resultError(error){
    const result=
        document.querySelector(
            "#result"
        );

    if(result){
        result.textContent=
            `server said no ⊹ ${error.message}`;
    }
}

function fail(error){
    stop();

    app.innerHTML=`
        <div class="error">
            <h1>🕯️ parlor</h1>

            <p>
                rosie tripped over the furniture
            </p>

            <code>
                ${String(
                    error.message
                    ||error
                )}
            </code>
        </div>
    `;
}

async function boot(){
    try{
        await discordSdk.ready();

        const {code}=
            await discordSdk.commands.authorize({
                client_id:
                    CLIENT_ID,

                response_type:
                    "code",

                state:
                    "",

                prompt:
                    "none",

                scope:[
                    "identify"
                ]
            });

        const response=
            await fetch(
                "/.proxy/api/token",
                {
                    method:
                        "POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            code,
                            instance_id:(
                                discordSdk.instanceId
                                ||new URLSearchParams(
                                    window.location.search
                                ).get(
                                    "instance_id"
                                )
                            )
                        })
                }
            );

        const token=
            await readjson(
                response
            );

        if(!response.ok){
            throw new Error(
                token.error
                ||"authentication failed"
            );
        }

        const auth=
            await discordSdk.commands.authenticate({
                access_token:
                    token.access_token
            });

        if(!auth){
            throw new Error(
                "Discord authentication failed"
            );
        }

        session=
            token.session;

        user=
            token.user;

        parlor();

    }catch(error){
        console.error(
            error
        );

        fail(
            error
        );
    }
}

window.addEventListener(
    "keydown",
    event=>{
        if(
            screen!=="soaring"
            || event.repeat
            || (
                event.code!=="Space"
                && event.code!=="ArrowUp"
            )
        ){
            return;
        }

        event.preventDefault();

        flap();
    }
);

boot();
