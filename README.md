# nvp_offline_film
The neural virtual production (NVP) is a AI coded film studio utilizing a VLM to realize serious film production. The goal of the creation of a NVP that features data accuracy, consistency and a production bible was made for serious AI film making. The NVP will be an offline model utiling a VLM and other tools. The NVP has files that will enforce certain rules to ensure consistency. The NVP relies on the demployment of AI agents to perform certain roles like director (orchestrator), DP (director of photography), acting coach, script supervisor, asset management and etc. I have worked on it and may continue to work on it. It features asynchronous process with scaling in mind and potential deployment into a distributed computing environment utilizing interconnected mutlicore and multi-gpu machines.

The NVP was created using Google Gemini. I tried my best to make sure Gemini Pro Extended Thinking would do the bulk of the coding and drafting of JSON files for the frontend and backend of the NVP.

My motivation to make a NVP was due to my frustration with commercial cloud film platforms like RunwayML and Google Flow. I can tell the development team do not have an understanding of how film is made. Serious film making is so much more than AI generated film clips that are 4s to 10s long then stitched together. In actual film making, you have an idea. You can turn your idea into a script or just film it. But in film making, you have a scene. A scene is made up of the location and characters. These characters are the principal actors (actors who say lines) and background actors (actors or people who do not have lines and help create an environment). If there is a script, the script has sluglines. These sluglines contain information on a scene. The script has lines that the principal actors say. Platforms like Google Flow cannot distinguish who says what lines and sometimes you have the wrong characters saying the wrong lines. Theses scenes are building blocks for the film or TV series. Another issue with Google Flow and other AI generated video content is that the characters are not consistant. From use, I noticed that the generative AI videos reason in 2D. You can tell because the characters will walk through objects and this happen consistently where it revealed current generative AI lack 3D spatial awareness. This prompted me to utilize a 3D engine like Unreal Engine 5 (UE5) to build the location and the characters. In the scene, a virtual camera is added to film the screen and convert the data into 2D. In fact, multiple virtual cameras could be deployed.

#                                                           #
#                Software License and TOS                   #
#                                                           #

TLDR - You pay for the executable, you can use it. The source code is off limits. No software subscription, no license fees. One time purchase for lifetime, unlimited use for only one real person and not a ficticious entity. You cannot hold me liable for the stupid stuff you do with this software after purchase.

The Software License? I do not have a formal one but this software is proprietary. I do not grant the license for others to use this software, whether partially or full, without payment. I do not grant permission to access the source code. I do not grant the permission to modify and/or change the soure code. I do not grant permission to share my source code, either in partially or in its entirety, the NVP architect. I do not grant the permission to improve on this code. All these things can be waived only by the dev, Michael Vang.

Only the executiable software will be available for purchase. If the executable software is purchased, I  grant single unlimited, lifetime use, private or commercial, to a single real person. Any ficticious entity or person must purchase the software for everybody that will use it. Real means a real, single human being -  a single human that is not a legal business i.e. sole proprietor or LLC. The word "ficticious" recognizes a business whether sole proprietor, partnerships, limited liability corporation (LLC), corporations (S, C or etc.) or any other legal business formation (benefit corporation, for profit, not-for-profit, non-profit or etc.). This statement is trying to communicate 2 things: 1. if someone wants to use this software, they have to buy their own copy. If a business wants to buy it for their team, they have to buy a copy for everyone that is going to use it. I do not like software subscription models and prefer the retail model of buying once with unlimited use until a person dies. So even if it is 50 years from now and a person wants to install and run it, that person can. I know I could rake in the money with software licenses but I don't really care. 

You do not have the license to pirate this NVP software, whether partially or full software, or use the software without purchase.

You do not have the license to clone or copy this repository at all whatsoever so help you God, on yo momma.

You do not have the license to backward engineer this software or even make an attempt.

When the dev(s), excluding AI, decides to make the software open source, that branch that is open source will be licensed under an open source license. Until then, this repository is private and proprietary.

If the dev(s), excluding AI, has met his/our untimely death, this codebase will fall into the public domain immediately.

You buying this software to use it is assumed to be in good faith. You will assume any and all responsibility, accountability, liability and culpability, good or bad, for how you use this software. I made this software in good faith for personal use and with no ill intent. It is up to you the user to double check to integrity of the software incase someone tampered with it maliciously. And this is my CYA, I am not responsible, accountable, liabilbe and culpable, good or bad, for how you use this software.

Ex.1 if you use my software and make $1 million. You made that and I cannot ask for a cut.
Ex.2 if you use my software for evil, and you get sued and/or get incarcerate or worse things happen, that was your by own choice(s) and you cannot hold me responsible, accountable, liable and culpable for your poor life decision(s) even if you claim insanity.

#                                                           #
#                       Requirements                        #
#                                                           #

It is recommended to get a workstation grade CPU or server grade CPU like an AMD Threadripper Pro and a workstation grade motherboard. You will need as many PCIe lanes as possible. Recommended at least PCIe 4.0 to get started.
System RAM of more than 32GB DDR4 ECC RDIMM or server grade memory modules. A single bit flip error could derail any processing and create errors.
A nVidia Tesla V100 is okay but a nVidia RTX 3090 with a NVLINK would be suitable. Recommended newer generation graphics card or AI accelerator card. Meaning at least a A100 or at least a RTX 5060. The best would obviously be the Blackwell Tesla H200.
A NVMe solid state drive of 2TB.

Minimum Specs
AMD THreadripper Pro 3000 series or equivalent
32GB DDR4 ECC RDIMM
nVidia Tesla V100 16GB HBM  or equivalent
NVMe SSD 1TB

Recommended Specs
AMD Threadripper Pro 7000 series  or equivalent
128GB DDR5 ECC RDIMM
nVidia Tsela A100 or RTX 5090 32GB GDDR7X  or equivalent
NVMe SSD 2TB
