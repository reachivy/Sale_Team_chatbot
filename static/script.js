const startBtn = document.getElementById('startBtn');
const submitBtn = document.getElementById('submitBtn');
const micBtn = document.getElementById('micBtn');
const timerEl = document.getElementById('timer');
const sectionEl = document.getElementById('sectionArea');
const chatboxEl = document.getElementById('chatbox');
const statusEl = document.getElementById('status');
const textAnswer = document.getElementById('textAnswer');
const inputArea = document.getElementById('inputArea');
const greetingEl = document.getElementById('greeting');
const progressEl = document.getElementById('progress');
const wordCountEl = document.getElementById('wordCount');
const sectionCompleteArea = document.getElementById('sectionCompleteArea');
const sectionCompleteTitle = document.getElementById('sectionCompleteTitle');
const sectionScoreEl = document.getElementById('sectionScore');
const reattemptBtn = document.getElementById('reattemptBtn');
const nextSectionBtn = document.getElementById('nextSectionBtn');
const sectionLinks = document.querySelectorAll('.section-link');
const dropdownBtns = document.querySelectorAll('.dropdown-btn');
const questionLinks = document.querySelectorAll('.question-link');
const feedbackEl = document.createElement('p');
feedbackEl.id = 'sectionFeedback';
let synth = window.speechSynthesis;

// Create an element for displaying question scores
const questionScoresEl = document.createElement('div');
questionScoresEl.id = 'questionScores';
questionScoresEl.style.display = 'flex';
questionScoresEl.style.flexWrap = 'wrap';
questionScoresEl.style.gap = '10px 20px';
questionScoresEl.style.marginBottom = '20px';
questionScoresEl.style.fontSize = '16px';
questionScoresEl.style.color = '#2c3e50';

// Speech Recognition setup for transcription
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;  // Set to true to continue listening until manually stopped
    recognition.interimResults = false;
    recognition.lang = 'en-US';
} else {
    console.error('SpeechRecognition API not supported in this browser.');
}

let currentQuestionNumber = 0;
let timerInterval = null;
let elapsedTime = 0; // Track total elapsed time for the current recording session
let isRecording = false;
let mediaRecorder = null;
let audioContext = null;
let analyser = null;
let audioChunks = [];
let audioData = [];
let stream = null;
let transcriptBuffer = [];  // To store transcriptions during the recording session

sectionCompleteArea.insertBefore(feedbackEl, sectionScoreEl.nextSibling);
sectionCompleteArea.insertBefore(questionScoresEl, feedbackEl); // Insert questionScoresEl between sectionScoreEl and feedbackEl

// Toggle dropdown visibility
dropdownBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const dropdown = btn.parentElement.nextElementSibling;
        dropdown.classList.toggle('hidden');
        btn.classList.toggle('open');
    });
});

// Handle section link clicks
sectionLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const section = parseInt(link.getAttribute('data-section'));
        console.log(`Section link clicked: Section ${section}`);
        jumpToSection(section);
    });
});

// Handle question number clicks
questionLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const section = parseInt(link.getAttribute('data-section'));
        const questionNumber = parseInt(link.getAttribute('data-question'));
        console.log(`Question link clicked: Section ${section}, Question ${questionNumber}`);
        jumpToQuestion(section, questionNumber);
    });
});

startBtn.addEventListener('click', () => {
    console.log('Start button clicked');
    fetch('/start_assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'intern1' })
    })
    .then(response => {
        console.log('Start response:', response);
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        console.log('Start data received:', data);
        sectionEl.textContent = `Section ${data.section}: ${data.section_name}`;
        appendBotMessage(`Question ${data.display_question_number}: ${data.question}`);
        progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
        currentQuestionNumber = data.question_number;
        speakQuestion(data.question);
        startBtn.style.display = 'none';
        greetingEl.parentElement.style.display = 'none';
        inputArea.style.display = 'block';
        sectionCompleteArea.style.display = 'none';
        chatboxEl.style.display = 'block';
    })
    .catch(error => console.error('Start error:', error));
});

micBtn.addEventListener('click', () => {
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
});

async function startRecording() {
    try {
        console.log('Starting recording');
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        transcriptBuffer = [];  // Reset transcript buffer at the start of recording

        // Set up Web Audio API for tone and confidence analysis
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 2048;
        audioData = new Float32Array(analyser.frequencyBinCount);

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            console.log('Recording stopped');
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });

            // Analyze audio for tone and confidence
            const { toneScore, confidenceScore, toneDetails, confidenceDetails } = await analyzeAudio(audioBlob);

            // Store tone and confidence results for submission
            textAnswer.dataset.toneScore = toneScore;
            textAnswer.dataset.confidenceScore = confidenceScore;
            textAnswer.dataset.toneDetails = toneDetails;
            textAnswer.dataset.confidenceDetails = confidenceDetails;
            textAnswer.dataset.responseTime = elapsedTime; // Store total response time

            // Append the full transcript to the input box when recording stops
            const finalTranscript = transcriptBuffer.join(' ').trim();
            if (finalTranscript) {
                const currentText = textAnswer.value.trim();
                textAnswer.value = currentText ? currentText + ' ' + finalTranscript : finalTranscript;
                const words = textAnswer.value.trim().split(/\s+/).filter(word => word.length > 0).length;
                wordCountEl.textContent = `${words} words`;
            }
        };

        // Start SpeechRecognition for transcription
        if (recognition) {
            recognition.onresult = (event) => {
                const transcript = event.results[event.results.length - 1][0].transcript;
                console.log('Transcription received:', transcript);
                transcriptBuffer.push(transcript);  // Collect transcriptions in the buffer
            };

            recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                statusEl.textContent = 'Error with speech recognition: ' + event.error;
            };

            recognition.onend = () => {
                console.log('Speech recognition ended');
                // Restart recognition if still recording (e.g., after a pause)
                if (isRecording && elapsedTime < 30) {
                    console.log('Restarting speech recognition due to pause');
                    recognition.start();
                }
            };

            recognition.start();
            console.log('Speech recognition started');
        } else {
            statusEl.textContent = 'Speech recognition not supported. Please type your answer.';
        }

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        startTimer();
    } catch (error) {
        console.error('Error starting recording:', error);
        statusEl.textContent = 'Error accessing microphone. Please try again.';
    }
}

function stopRecording() {
    console.log('Stopping recording');
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    if (recognition) {
        recognition.stop();
    }
    isRecording = false;
    micBtn.classList.remove('recording');
    stopTimer();
}

async function analyzeAudio(audioBlob) {
    // Create an AudioContext to decode the audio blob
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const arrayBuffer = await audioBlob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    // Set up analyser
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Float32Array(bufferLength);
    const timeDomainData = new Float32Array(bufferLength);

    // Create a source from the audio buffer
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(analyser);
    analyser.connect(audioContext.destination);

    // Variables for analysis
    let volumeSamples = [];
    let pitchSamples = [];
    let speakingTime = 0;
    let silenceTime = 0;
    let lastSoundTime = null;
    const silenceThreshold = -50; // dB threshold for silence
    const sampleRate = audioContext.sampleRate;
    const duration = audioBuffer.duration;
    const frameDuration = bufferLength / sampleRate; // Duration of each frame in seconds
    let currentTime = 0;

    // Process the audio buffer in chunks
    const processAudio = () => {
        return new Promise((resolve) => {
            while (currentTime < duration) {
                // Simulate playback by advancing time
                const offset = currentTime * sampleRate;
                const remainingSamples = audioBuffer.length - offset;
                const samplesToProcess = Math.min(bufferLength, remainingSamples);

                // Extract time-domain data for the current frame
                const channelData = audioBuffer.getChannelData(0).slice(offset, offset + samplesToProcess);
                for (let i = 0; i < bufferLength; i++) {
                    timeDomainData[i] = i < channelData.length ? channelData[i] : 0;
                }

                // Calculate volume (RMS)
                let sumSquares = 0;
                for (let i = 0; i < bufferLength; i++) {
                    sumSquares += timeDomainData[i] * timeDomainData[i];
                }
                const volume = 20 * Math.log10(Math.sqrt(sumSquares / bufferLength));
                if (!isNaN(volume) && volume > -Infinity) {
                    volumeSamples.push(volume);
                }

                // Estimate pitch using autocorrelation
                let maxCorrelation = 0;
                let bestLag = 0;
                for (let lag = 20; lag < bufferLength / 2; lag++) {
                    let correlation = 0;
                    for (let i = 0; i < bufferLength - lag; i++) {
                        correlation += timeDomainData[i] * timeDomainData[i + lag];
                    }
                    if (correlation > maxCorrelation) {
                        maxCorrelation = correlation;
                        bestLag = lag;
                    }
                }
                const pitch = bestLag > 0 ? sampleRate / bestLag : 0;
                if (pitch > 0 && pitch < 500) { // Reasonable pitch range for human voice
                    pitchSamples.push(pitch);
                }

                // Detect silence
                if (volume > silenceThreshold) {
                    if (lastSoundTime !== null) {
                        silenceTime += currentTime - lastSoundTime;
                    }
                    lastSoundTime = currentTime;
                    speakingTime += frameDuration;
                }

                currentTime += frameDuration;
            }

            // Calculate tone and confidence scores
            const toneScore = calculateToneScore(pitchSamples);
            const confidenceScore = calculateConfidenceScore(volumeSamples, speakingTime, silenceTime, duration);
            const toneDetails = generateToneFeedback(toneScore, pitchSamples);
            const confidenceDetails = generateConfidenceFeedback(confidenceScore, volumeSamples, speakingTime, silenceTime);

            resolve({ toneScore, confidenceScore, toneDetails, confidenceDetails });
        });
    };

    const result = await processAudio();
    await audioContext.close();
    return result;
}

function calculateToneScore(pitchSamples) {
    if (pitchSamples.length === 0) return 0;
    const meanPitch = pitchSamples.reduce((sum, val) => sum + val, 0) / pitchSamples.length;
    const variance = pitchSamples.reduce((sum, val) => sum + Math.pow(val - meanPitch, 2), 0) / pitchSamples.length;
    const stdDev = Math.sqrt(variance);
    const variationRatio = Math.min((stdDev / meanPitch) * 10, 1);
    let score = variationRatio * 100;
    return Math.max(0, Math.min(100, Math.round(score)));
}

function calculateConfidenceScore(volumeSamples, speakingTime, silenceTime, totalDuration) {
    if (volumeSamples.length === 0) return 0;
    const meanVolume = volumeSamples.reduce((sum, val) => sum + val, 0) / volumeSamples.length;
    const volumeVariance = volumeSamples.reduce((sum, val) => sum + Math.pow(val - meanVolume, 2), 0) / volumeSamples.length;
    const volumeStdDev = Math.sqrt(volumeVariance);
    const speakingRate = speakingTime / totalDuration;
    const silenceRatio = silenceTime / totalDuration;

    let score = 100;
    if (volumeStdDev / meanVolume > 0.3) score -= 33;
    if (speakingRate < 0.4 || speakingRate > 0.8) score -= 33;
    if (silenceRatio > 0.3) score -= 33;
    return Math.max(0, Math.min(100, Math.round(score)));
}

function generateToneFeedback(toneScore, pitchSamples) {
    if (pitchSamples.length === 0) return "No audio recorded. Tone analysis requires a spoken response using the microphone.";
    if (toneScore >= 80) {
        return "Tone: Excellent - Your tone is expressive and engaging with good pitch variation.";
    } else if (toneScore >= 60) {
        return "Tone: Good - Your tone has some variation, but could be more expressive.";
    } else if (toneScore >= 40) {
        return "Tone: Fair - Your tone is somewhat monotone; try varying your pitch more.";
    } else {
        return "Tone: Needs Improvement - Your tone is very monotone, which may reduce engagement.";
    }
}

function generateConfidenceFeedback(confidenceScore, volumeSamples, speakingTime, silenceTime) {
    let details = [];
    if (volumeSamples.length > 0) {
        const volumeVariance = volumeSamples.reduce((sum, val) => sum + Math.pow(val - volumeSamples.reduce((a, b) => a + b, 0) / volumeSamples.length, 2), 0) / volumeSamples.length;
        if (Math.sqrt(volumeVariance) / (volumeSamples.reduce((a, b) => a + b, 0) / volumeSamples.length) > 0.3) {
            details.push("Your volume varies significantly, which may suggest hesitation.");
        }
    } else {
        return "No audio recorded. Confidence analysis requires a spoken response using the microphone.";
    }
    const speakingRate = speakingTime / (speakingTime + silenceTime);
    if (speakingRate < 0.4) details.push("You spoke too slowly, which may indicate uncertainty.");
    if (speakingRate > 0.8) details.push("You spoke too quickly, which may suggest nervousness.");
    if (silenceTime / (speakingTime + silenceTime) > 0.3) details.push("There were excessive pauses, which may reduce perceived confidence.");

    if (confidenceScore >= 80) {
        return "Confidence: Excellent - You spoke confidently with consistent volume and pacing.\n" + details.join("\n");
    } else if (confidenceScore >= 60) {
        return "Confidence: Good - Your confidence is solid, but there are areas to improve.\n" + details.join("\n");
    } else if (confidenceScore >= 40) {
        return "Confidence: Fair - Your confidence needs improvement; focus on pacing and consistency.\n" + details.join("\n");
    } else {
        return "Confidence: Needs Improvement - Your delivery lacks confidence; work on reducing pauses and maintaining steady volume.\n" + details.join("\n");
    }
}

submitBtn.addEventListener('click', () => {
    const answer = textAnswer.value.trim();
    if (answer) {
        console.log('Text input:', answer);
        const toneScore = textAnswer.dataset.toneScore || 0;
        const confidenceScore = textAnswer.dataset.confidenceScore || 0;
        const toneDetails = textAnswer.dataset.toneDetails || "No audio recorded. Tone analysis requires a spoken response using the microphone.";
        const confidenceDetails = textAnswer.dataset.confidenceDetails || "No audio recorded. Confidence analysis requires a spoken response using the microphone.";
        const responseTime = textAnswer.dataset.responseTime || 0;
        submitAnswer(answer, toneScore, confidenceScore, toneDetails, confidenceDetails, responseTime);
        appendUserMessage(answer);
        textAnswer.value = '';
        wordCountEl.textContent = '0 words';
        delete textAnswer.dataset.toneScore;
        delete textAnswer.dataset.confidenceScore;
        delete textAnswer.dataset.toneDetails;
        delete textAnswer.dataset.confidenceDetails;
        delete textAnswer.dataset.responseTime;
    } else {
        statusEl.textContent = 'Please enter an answer.';
    }
});

textAnswer.addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault();
        const answer = textAnswer.value.trim();
        if (answer) {
            console.log('Enter key pressed, submitting:', answer);
            const toneScore = textAnswer.dataset.toneScore || 0;
            const confidenceScore = textAnswer.dataset.confidenceScore || 0;
            const toneDetails = textAnswer.dataset.toneDetails || "No audio recorded. Tone analysis requires a spoken response using the microphone.";
            const confidenceDetails = textAnswer.dataset.confidenceDetails || "No audio recorded. Confidence analysis requires a spoken response using the microphone.";
            const responseTime = textAnswer.dataset.responseTime || 0;
            submitAnswer(answer, toneScore, confidenceScore, toneDetails, confidenceDetails, responseTime);
            appendUserMessage(answer);
            textAnswer.value = '';
            wordCountEl.textContent = '0 words';
            delete textAnswer.dataset.toneScore;
            delete textAnswer.dataset.confidenceScore;
            delete textAnswer.dataset.toneDetails;
            delete textAnswer.dataset.confidenceDetails;
            delete textAnswer.dataset.responseTime;
        } else {
            statusEl.textContent = 'Please enter an answer.';
        }
    }
});

textAnswer.addEventListener('input', () => {
    const words = textAnswer.value.trim().split(/\s+/).filter(word => word.length > 0).length;
    wordCountEl.textContent = `${words} words`;
});

reattemptBtn.addEventListener('click', () => {
    console.log('Reattempt button clicked for current section');
    fetch('/start_assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'intern1' })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        console.log('Reattempt data received:', data);
        sectionEl.textContent = `Section ${data.section}: ${data.section_name}`;
        chatboxEl.innerHTML = '';
        appendBotMessage(`Question ${data.display_question_number}: ${data.question}`);
        progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
        currentQuestionNumber = data.question_number;
        speakQuestion(data.question);
        sectionCompleteArea.style.display = 'none';
        chatboxEl.style.display = 'block';
        inputArea.style.display = 'block';
        statusEl.textContent = '';
    })
    .catch(error => console.error('Reattempt error:', error));
});

nextSectionBtn.addEventListener('click', () => {
    console.log('Next section button clicked');
    fetch('/start_assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'intern1' })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(nextData => {
        console.log('Next section data received:', nextData);
        sectionEl.textContent = `Section ${nextData.section}: ${nextData.section_name}`;
        chatboxEl.innerHTML = '';
        appendBotMessage(`Question ${nextData.display_question_number}: ${nextData.question}`);
        progressEl.textContent = `${nextData.answered}/${data.total_questions} answered`;
        currentQuestionNumber = nextData.question_number;
        speakQuestion(nextData.question);
        sectionCompleteArea.style.display = 'none';
        chatboxEl.style.display = 'block';
        inputArea.style.display = 'block';
        statusEl.textContent = '';
    })
    .catch(error => console.error('Next section error:', error));
});

function startTimer() {
    elapsedTime = 0; // Reset elapsed time at the start of a new recording session
    timerEl.textContent = `${elapsedTime}s`;
    timerEl.classList.add('active');
    timerInterval = setInterval(() => {
        elapsedTime++;
        timerEl.textContent = `${elapsedTime}s`;
        if (elapsedTime >= 30) {
            stopRecording(); // Automatically stop at 30 seconds
        }
    }, 1000);
}

function stopTimer() {
    clearInterval(timerInterval);
    timerEl.classList.remove('active');
}

function appendBotMessage(message, className = '', detailedFeedback = '') {
    if (!message) {
        console.log('Attempted to append empty message with class:', className);
        return;
    }
    const messageDiv = document.createElement('div');
    messageDiv.className = 'chat-message bot-message';
    const messageWrapper = document.createElement('div');
    messageWrapper.className = 'message-wrapper';
    const messageP = document.createElement('p');
    messageP.textContent = message;
    if (className) {
        messageP.className = className;
    }
    messageWrapper.appendChild(messageP);
    if ((className === 'content-accuracy' || className === 'clarity' || className === 'language' || className === 'tone-confidence' || className === 'match-percentage') && detailedFeedback) {
        const showMoreBtn = document.createElement('span');
        showMoreBtn.className = 'show-more-btn';
        showMoreBtn.textContent = '+';
        messageP.appendChild(showMoreBtn);
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'detailed-feedback hidden';
        feedbackDiv.textContent = detailedFeedback;
        messageWrapper.appendChild(feedbackDiv);
        showMoreBtn.addEventListener('click', () => {
            feedbackDiv.classList.toggle('hidden');
            showMoreBtn.textContent = feedbackDiv.classList.contains('hidden') ? '+' : '−';
        });
    }
    messageDiv.appendChild(messageWrapper);
    chatboxEl.appendChild(messageDiv);
    chatboxEl.scrollTop = chatboxEl.scrollHeight;
    console.log('Appended bot message:', message, 'with class:', className);
    console.log('Chatbox HTML after appending:', chatboxEl.innerHTML);
}

function appendUserMessage(message) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'chat-message user-message';
    const messageP = document.createElement('p');
    messageP.textContent = message;
    messageDiv.appendChild(messageP);
    chatboxEl.appendChild(messageDiv);
    chatboxEl.scrollTop = chatboxEl.scrollHeight;
    console.log('Appended user message:', message);
}

function submitAnswer(answer, toneScore, confidenceScore, toneDetails, confidenceDetails, responseTime) {
    console.log('Submitting answer:', answer, 'for question number:', currentQuestionNumber);
    fetch('/submit_answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: 'intern1',
            answer: answer,
            question_number: currentQuestionNumber,
            tone_score: toneScore,
            confidence_score: confidenceScore,
            tone_details: toneDetails,
            confidence_details: confidenceDetails,
            response_time: responseTime // Pass the response time to the backend
        })
    })
    .then(response => {
        console.log('Submit response:', response);
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.error || 'Network response was not ok');
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Submit data received:', data);
        if (data.status === 'section_completed') {
            console.log('Section completed, hiding chatbox and input area, showing section complete area');
            progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
            setTimeout(() => {
                chatboxEl.style.display = 'none';
                console.log('Chatbox display set to none, current style:', chatboxEl.style.display);
                inputArea.style.display = 'none';
                console.log('Input area display set to none, current style:', inputArea.style.display);
                sectionCompleteArea.style.display = 'block';
                console.log('Section complete area display set to block, current style:', sectionCompleteArea.style.display);
                sectionCompleteTitle.textContent = `Section ${data.section - (data.section_score >= 75 ? 1 : 0)} (${data.section_name}) Completed!`;
                sectionScoreEl.textContent = `Your Score: ${data.section_score.toFixed(2)}%`;

                // Display question scores in a two-column format
                questionScoresEl.innerHTML = ''; // Clear previous content
                const scores = data.question_scores || [];
                for (let i = 0; i < scores.length; i += 2) {
                    const rowDiv = document.createElement('div');
                    rowDiv.style.display = 'flex';
                    rowDiv.style.width = '100%';
                    rowDiv.style.justifyContent = 'space-between';

                    // First column
                    const leftDiv = document.createElement('div');
                    leftDiv.style.flex = '1';
                    leftDiv.textContent = `Question ${scores[i].question_number} (${scores[i].score} points)`;
                    rowDiv.appendChild(leftDiv);

                    // Second column (if exists)
                    if (i + 1 < scores.length) {
                        const rightDiv = document.createElement('div');
                        rightDiv.style.flex = '1';
                        rightDiv.style.textAlign = 'right';
                        rightDiv.textContent = `Question ${scores[i + 1].question_number} (${scores[i + 1].score} points)`;
                        rowDiv.appendChild(rightDiv);
                    }

                    questionScoresEl.appendChild(rowDiv);
                }

                if (data.feedback) {
                    feedbackEl.textContent = data.feedback;
                    feedbackEl.style.display = 'block';
                } else {
                    feedbackEl.textContent = '';
                    feedbackEl.style.display = 'none';
                }
                if (data.section_score >= 75) {
                    console.log('Score >= 75, showing next section button');
                    nextSectionBtn.style.display = 'inline-block';
                    reattemptBtn.style.display = 'none';
                } else {
                    console.log('Score < 75, showing reattempt button');
                    reattemptBtn.style.display = 'inline-block';
                    nextSectionBtn.style.display = 'none';
                }
                statusEl.textContent = '';
            }, 2000);
        } else if (data.status === 'completed') {
            console.log('Assessment completed, hiding chatbox and showing final scores');
            progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
            setTimeout(() => {
                chatboxEl.style.display = 'none';
                console.log('Chatbox display set to none, current style:', chatboxEl.style.display);
                inputArea.style.display = 'none';
                console.log('Input area display set to none, current style:', inputArea.style.display);
                sectionCompleteArea.style.display = 'block';
                console.log('Section complete area display set to block, current style:', sectionCompleteArea.style.display);
                sectionCompleteTitle.textContent = 'Assessment Completed!';
                sectionScoreEl.textContent = 'Final Scores: ' + JSON.stringify(data.scores);
                questionScoresEl.innerHTML = ''; // Clear question scores
                feedbackEl.textContent = '';
                feedbackEl.style.display = 'none';
                reattemptBtn.style.display = 'none';
                nextSectionBtn.style.display = 'none';
                statusEl.textContent = '';
            }, 2000);
        } else {
            chatboxEl.style.display = 'block';
            console.log('Chatbox visibility before appending feedback:', chatboxEl.style.display);
            appendBotMessage(`You earned ${data.score_points} points for this answer (Match: ${data.match_percentage.toFixed(2)}%)`, 'match-percentage');
            console.log('Content Accuracy Feedback:', data.content_accuracy);
            if (data.content_accuracy) {
                appendBotMessage(data.content_accuracy, 'content-accuracy', data.detailed_feedback);
            } else {
                console.log('No content_accuracy feedback received');
                appendBotMessage('Error: Content Accuracy feedback is missing.', 'content-accuracy');
            }
            console.log('Clarity Feedback:', data.clarity_feedback);
            console.log('Language Feedback:', data.language_feedback);
            if (data.clarity_feedback) {
                const clarityDetails = `Clarity Issues:\n${data.clarity_details}`;
                appendBotMessage(data.clarity_feedback, 'clarity', clarityDetails);
            } else {
                console.log('No clarity feedback received');
                appendBotMessage('Error: Clarity feedback is missing.', 'clarity');
            }
            if (data.language_feedback) {
                const languageDetails = `Language Issues:\n${data.language_details}`;
                appendBotMessage(data.language_feedback, 'language', languageDetails);
            } else {
                console.log('No language feedback received');
                appendBotMessage('Error: Language feedback is missing.', 'language');
            }
            console.log('Tone Feedback:', data.tone_feedback);
            console.log('Confidence Feedback:', data.confidence_feedback);
            if (data.tone_feedback && data.confidence_feedback) {
                const toneConfidenceFeedback = `${data.tone_feedback} | ${data.confidence_feedback}`;
                const toneConfidenceDetails = `Tone Details:\n${data.tone_details}\n\nConfidence Details:\n${data.confidence_details}\n\nResponse Time: You took ${responseTime} seconds to answer this question.`;
                appendBotMessage(toneConfidenceFeedback, 'tone-confidence', toneConfidenceDetails);
            } else {
                console.log('No tone or confidence feedback received');
                appendBotMessage('Error: Tone and Confidence feedback is missing.', 'tone-confidence');
            }
            setTimeout(() => {
                sectionEl.textContent = `Section ${data.section}: ${data.section_name}`;
                appendBotMessage(`Question ${data.display_question_number}: ${data.question}`);
                progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
                currentQuestionNumber = data.question_number;
                speakQuestion(data.question);
                statusEl.textContent = '';
                sectionCompleteArea.style.display = 'none';
                chatboxEl.style.display = 'block';
                inputArea.style.display = 'block';
            }, 2000);
        }
    })
    .then(() => {
        console.log('Post-submit UI state - Chatbox:', chatboxEl.style.display, 'Section Complete Area:', sectionCompleteArea.style.display);
    })
    .catch(error => {
        console.error('Submit error:', error);
        const errorMessage = error.message === 'Network response was not ok' ? 'Error: Failed to submit answer.' : `Error: ${error.message}`;
        appendBotMessage(errorMessage, 'error-message');
    });
}

function speakQuestion(text) {
    console.log('Speaking:', text);
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    synth.speak(utterance);
}

function jumpToSection(section) {
    fetch('/start_assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'intern1', section: section })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        console.log('Jump to section data received:', data);
        sectionEl.textContent = `Section ${data.section}: ${data.section_name}`;
        chatboxEl.innerHTML = '';
        appendBotMessage(`Question ${data.display_question_number}: ${data.question}`);
        progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
        currentQuestionNumber = data.question_number;
        speakQuestion(data.question);
        sectionCompleteArea.style.display = 'none';
        chatboxEl.style.display = 'block';
        inputArea.style.display = 'block';
        statusEl.textContent = '';
        startBtn.style.display = 'none';
        greetingEl.parentElement.style.display = 'none';
    })
    .catch(error => console.error('Jump to section error:', error));
}

function jumpToQuestion(section, questionNumber) {
    // First, ensure the section is set
    fetch('/start_assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'intern1', section: section })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(() => {
        // Now fetch the specific question
        fetch('/get_question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: 'intern1', question_number: questionNumber })
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            console.log('Jump to question data received:', data);
            sectionEl.textContent = `Section ${data.section}: ${data.section_name}`;
            chatboxEl.innerHTML = '';
            appendBotMessage(`Question ${data.display_question_number}: ${data.question}`);
            progressEl.textContent = `${data.answered}/${data.total_questions} answered`;
            currentQuestionNumber = data.question_number;
            speakQuestion(data.question);
            sectionCompleteArea.style.display = 'none';
            chatboxEl.style.display = 'block';
            inputArea.style.display = 'block';
            statusEl.textContent = '';
            startBtn.style.display = 'none';
            greetingEl.parentElement.style.display = 'none';
        })
        .catch(error => console.error('Jump to question error:', error));
    })
    .catch(error => console.error('Set section error:', error));
}