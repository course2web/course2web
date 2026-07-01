import groovyx.net.http.*; 
import static groovyx.net.http.ContentType.*;
import static groovyx.net.http.Method.*;
import au.com.bytecode.opencsv.CSVParser;
import org.apache.commons.io.FileUtils;
import org.apache.velocity.app.Velocity;
import org.apache.velocity.Template;
import org.apache.velocity.context.Context;
import org.apache.velocity.VelocityContext;

import org.apache.commons.lang.StringUtils;
import com.fasterxml.jackson.databind.ObjectMapper;
import groovy.json.*;

def ops = []
ops.add("print");
ops.add("audio");
//ops.add("zip");
ops.add("docs");
ops.add("json");
//ops.add("wp");
ops.add("podcast");

configCreateAudioIfNewerThanMillis = Date.parse("MM/dd/yyyy", "12/23/2020").toCalendar().getTimeInMillis();

def mockRun = false;

def http = new HTTPBuilder( 'https://docs.google.com')

def objectMapper = new ObjectMapper(); 

/*
Date d2 = Date.parse("MM/dd/yyyy", '11/17/2012')
println d2.format("EEE, d MMM yyyy HH:mm:ss Z");
d2 = Date.parse("MM/dd/yyyy", '1/1/2012')
println d2.format("EEE, d MMM yyyy HH:mm:ss Z");
System.exit(1);
*/

/*
https://docs.google.com/spreadsheet/pub?key=0AkWmZX8HtwWHdENUNFcxdG9XdzBTaWhlVkZ0RU1QcXc&output=csv&single=true&gid=0
https://docs.google.com/spreadsheet/pub?key=0AkWmZX8HtwWHdENUNFcxdG9XdzBTaWhlVkZ0RU1QcXc&output=csv&single=true&gid=1
*/


def jsonClassArr = []
//for (gid in 5) {
// get these new gids from going to the spreadsheet and:
//  - File -> "Publish to the web..."
//  - Drop down "Entire Document" and select individuals
//for (gid in [0, 1, 2, 3, 4, 5, 6, 469482974, 827677169]) {
//for (gid in [827677169, 855509258, 6, 5, 4, 3, 2, 0, 1]) {
// 0 - missal
// 1 - uncovering_2011
// 2 - apologetics
// 3 - test
// 4 - Bible
// 5 - Sunday / Feasts
// 6 - Misc
// 7 - 469482974 - dailies
// 8 - 827677169 - uncovering-2015
// 9 - 728325633 - tyburn patrology
//     1233971849 - adult education
//     1501128082 - wed
// for (gid in [469482974]) {
//for (gid in [1]) {
for (gid in [1218728177, 1233971849, 1019442815, 1559662669, 1501128082, 827677169, 469482974, 6, 4, 3, 2, 0, 1]) {
//for (gid in [ 1019442815]) {
  println 'gid: '+gid;
  def responseStr = null;

  // perform a GET request, expecting JSON response data
  http.request( GET, TEXT ) {
    uri.path = '/spreadsheet/pub'
    uri.query = [ key:'0AkWmZX8HtwWHdENUNFcxdG9XdzBTaWhlVkZ0RU1QcXc', output: 'csv', single: true, gid: gid ]

    headers.'User-Agent' = 'Mozilla/5.0 Ubuntu/8.10 Firefox/3.0.4'

    response.success = { resp, reader ->
      assert resp.status == 200
      println "My response handler got response: ${resp.statusLine}"
      println "Response length: ${resp.headers.'Content-Length'}"
      responseStr = reader.getText() // print response reader
      println responseStr
    }
   
    // called only for a 404 (not found) status code:
    response.'404' = { resp ->
      println 'Not found'
    }

  }
  seriesLabels = [];
  seriesData = [:];
  classLabels = [];
  classes = [];
  CSVParser csvp = new CSVParser();
  responseStr.eachLine { line, lineNumber ->
    String[] cols = csvp.parseLine(line); 
    cols.eachWithIndex{ p, i -> 
      if (StringUtils.isEmpty(p)) {
        return false; 
      }
      if (lineNumber == 0) {
        seriesLabels[i] = p;
      } else if (lineNumber == 1) {
          seriesData.put(seriesLabels[i], p); 
      } else if (lineNumber == 2) {
        classLabels[i] = p;
      } else if (lineNumber >= 3) {
        if (classLabels[i].equals('id') && p.length() == 1) {
          p = '0'+p;
        }
        def row = classes[lineNumber - 3]
        if (row == null) {
          row = [:]
          classes.add(row);
        }
        def existingValue = row.get(classLabels[i]);
        if (existingValue != null) {
          if (existingValue instanceof java.util.List) {
            existingValue.add(p);
          } else {
            row.put(classLabels[i], [existingValue, p]);
          }
        } else {
          row.put(classLabels[i], p); 
        }
        if (classLabels[i].equals('date')) {
          Date d = Date.parse("MM/dd/yyyy", p)
          row.put('rssDate', d.format("EEE, d MMM yyyy HH:mm:ss Z"));
          row.put('dateId', d.format("yyyyMMdd"));
        }
        if (classLabels[i].equals('updated_on')) {
          Date d = null; 
          try {
            d = Date.parse("MM/dd/yyyy HH:mm:ss", p)
          } catch (Throwable t) {
            d = Date.parse("yyyy-MM-dd", p)
          }
          row.put('updated_on_date', d);
        }
      }
    };
  }

  def format = 'wp';
  "mkdir -p ./build/web/${seriesData.normalized_name}".execute().waitFor();
  "mkdir -p ./build/${seriesData.normalized_name}".execute().waitFor();

  for (c in classes) {
    if (c['id'] == null) {
      if (c['dateId'] != null) {
        c['id'] = c['dateId']
      } else if (c['audio'] ==~ '20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].*') {
        c['id'] = c['audio'].take(4) + c['audio'].drop(5).take(2) +  c['audio'].drop(8).take(2)
        Date d = Date.parse("yyyyMMdd", c['id'])
        c['date'] = d.format("MM/dd/yyyy");
        c['rssDate'] = d.format("EEE, d MMM yyyy HH:mm:ss Z");
        c['dateId'] = d.format("yyyyMMdd");
      }
    }
    if (c.title == null) {
      if (c['liturgical_day'] != null) {
        println ("c['liturgical_day']")
        println (c['liturgical_day'])
        if (c['liturgical_day'] instanceof Collection) {
          c.title = '';
          for (def i=0; i < c.liturgical_day.size; i++) {
            c.title += c.liturgical_day[i] + ' / ';
          }
          c.title = c.title.take((int) c.title.size() - 3);
        } else {
          c.title = c.liturgical_day;
        }
      }
    }
    if (c.audio) {
      c['newAudio'] = c.id +"-${seriesData.normalized_name}.mp3"
    }
    if (c.handout_file) {
      if (c.handout_file instanceof Collection) {
        c.new_handout_file = [];
        c.new_handout_title = [];
        for (def i=0; i<c.handout_file.size; i++) {
          c.new_handout_file[i] = getNewHandoutFileName(c.id, c.handout_title[i], c.handout_file[i]);
          c.new_handout_title[i] = c.handout_title[i]
        }
      } else {
        c.new_handout_file = [];
        c.new_handout_title = [c.handout_title];
        c.new_handout_file[0] = getNewHandoutFileName(c.id, c.handout_title, c.handout_file);
        c.handout_file = [c.handout_file];
        c.handout_title = [c.handout_title];
      }
    }
  }

  if ("TRUE".equals(seriesData["reverse_order"])) {
    classes = classes.reverse();
  }

  if (ops.contains('wp')) {
    runVelocity(
      "velocity/${format}.vm", 
      "build/web/${seriesData.normalized_name}/${format}.php",
      ["seriesData": seriesData, "classLabels": classLabels, "classes": classes]
    );
  }

  if (ops.contains('json')) {
    def jsonMap = [classes: classes, seriesData: seriesData]
    jsonClassArr.add(jsonMap);
  }

  if (ops.contains('print')) {
    println classLabels;
    println classes;
  }

  if (ops.contains('audio')) {
    /*
    "rm -fR ./build/${seriesData.normalized_name}/audio".execute().waitFor();
    */
    try {
      "mkdir -p ./build/${seriesData.normalized_name}/audio".execute().waitFor();
    } catch (t) {
      //do nothing
    }
    /*
    if (!new File("orig/${seriesData.normalized_name}").exists()) {
      def proc = "s3cmd sync s3://tedesche/${seriesData.normalized_name} ./orig".execute();
      proc.waitFor();
    }
    */
    for (c in classes) {
      if (c.audio) {
        def origFileStr = "orig/${seriesData.normalized_name}/audio/${c.audio}"
        def newFileStr = "build/${seriesData.normalized_name}/audio/${c.newAudio}"

        // if ref is youtube and origFile is missing, then generate it
        if (c.audio.contains('youtube')) {
            origFileStr = "orig/${seriesData.normalized_name}/audio/${c.newAudio}"
            if (!new File(origFileStr).exists()) {
                proc(["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", 
                    "--audio-quality", "0", "-o", origFileStr, c.audio])
            }
        }

        def createAudio = fileNewerThan(origFileStr, newFileStr, c.updated_on_date);

        println ("c.audio: ${c.audio}");
        println ("createAudio: ${createAudio}");
        if (c.volume_boost == null) {
          c.volume_boost = "2";
        }
        println ("c.volume_boost: ${c.volume_boost}");

        if (c['id'] == null) {
          c['id'] = origFileStr;
        }

        Date classDate = null;
        def shouldCreatePerConfig = false;
        try {
          classDate = Date.parse("EEE, d MMM yyyy HH:mm:ss Z", c['rssDate'])
          shouldCreatePerConfig = classDate.toCalendar().getTimeInMillis() > configCreateAudioIfNewerThanMillis;
          println ("shouldCreatePerConfig - 1: " + shouldCreatePerConfig)
          if (!shouldCreatePerConfig && c['updated_on_date']) {
          shouldCreatePerConfig = c['updated_on_date'].toCalendar().getTimeInMillis() > configCreateAudioIfNewerThanMillis;
            println ("shouldCreatePerConfig - updated_on_date: " + shouldCreatePerConfig)
          }
        } catch (e) {
          println ("no rssDate for c: " + c)
        }
        if (createAudio && !mockRun && shouldCreatePerConfig) {
          if (origFileStr ==~ '.*m4a') {
            println ('contains m4a!')
            newMp3AsOrig = origFileStr.replaceFirst(/m4a/, "mp3")
            proc(["ffmpeg", "-n", "-i", origFileStr, "-acodec", "libmp3lame", "-ab", "256k",  newMp3AsOrig]);
            origFileStr = newMp3AsOrig;
          } else {
            brokenOrigStr = origFileStr.replaceFirst(/.mp3/, "-broken.mp3")
            "mv ${origFileStr} ${brokenOrigStr}".execute().waitFor();
            proc(["ffmpeg", "-n", "-i", brokenOrigStr, "-acodec", "libmp3lame", "-ab", "256k",  origFileStr]);
            println ('no m4a!')
          }
          proc(["sox", "-v", c.volume_boost, origFileStr, "-r", "44.1k", "-c", "1", newFileStr]);
          proc(["id3v2", "-a", "David Tedesche", "-A", seriesData.normalized_name, "-t", c.title, "-T", c.id, newFileStr]);
        }
      }
    }
  }

  if (ops.contains('podcast')) {
    if (!mockRun) {
    /*
      if (fileNewerThanAll("build/${seriesData.normalized_name}/audio",
            "build/${seriesData.normalized_name}/podcast.xml" )) {
            */
        for (c in classes) {
          if (c.audio) {
            def newFile = "build/${seriesData.normalized_name}/audio/${c.newAudio}"
            if (new File(newFile).exists()) {
              def outStr = proc("soxi ${newFile}");
              def matcher = outStr =~ /Duration *: ([^ ]*) =/
              c["duration"] = matcher[0][1];
              c["length"] = proc("ls -lad ${newFile}").split(" ")[4]
              c["link2mp3"] = "/${seriesData.normalized_name}/audio/${c.newAudio}"
            }
          }
        }
        "mkdir -p ../web/${seriesData.normalized_name}".execute().waitFor();
        runVelocity(
          "velocity/podcast.vm", 
          "build/${seriesData.normalized_name}/podcast.xml",
          ["seriesData": seriesData, "classLabels": classLabels, "classes": classes]
        );
        "cp build/${seriesData.normalized_name}/podcast.xml build/${seriesData.normalized_name}/podcast-2.xml".execute().waitFor();
      //}
    }
  }

  if (ops.contains('docs') || ops.contains('zip')) {
    if (!mockRun) {
      "mkdir -p ./build/${seriesData.normalized_name}/docs".execute().waitFor();
      for (c in classes) {
        if (c.handout_file) {
          c.handout_links = [];
          for (def i=0; i<c.handout_file.size; i++) {
            def oldFile = c.handout_file[i].replaceAll('%20', ' ');
            if (oldFile.indexOf('http') == -1) {
              def hf = "./orig/${seriesData.normalized_name}/docs/${oldFile}"
              def nhf = "./build/${seriesData.normalized_name}/docs/${c.new_handout_file[i]}"
              c.handout_links[i] = "/${seriesData.normalized_name}/docs/${c.new_handout_file[i]}";
              if (fileNewerThan(hf, nhf, c.updated_on_date)) {
                proc(["cp", hf, nhf])
              }
            } else {
              c.handout_links[i] = c.handout_file[i];
            }
          }
        }
      }
    }
  }

  if (ops.contains('zip')) {
    if (seriesData["include_zips"] == null || !seriesData["include_zips"]) {
      for (zipDirStr in [ "docs", "audio" ] ) {
        //def zipFolderStr = "./build/${seriesData.normalized_name}/${zipDirStr}";
        def zipFolderStr = "${zipDirStr}";
        def zipFileStr = "./build/${seriesData.normalized_name}/${seriesData.normalized_name}-${zipDirStr}.zip" 
        if (fileNewerThanAll(zipFolderStr, zipFileStr)) {
          println "needToZip: ${zipFolderStr}"
          if (!mockRun) {
            proc("zip -rj ${zipFileStr} "+
              "./build/${seriesData.normalized_name}/${zipFolderStr}")
          }
        }
      }
    }
  }

  if (ops.contains('s3-publish')) {
    // put audio back to s3
    // put zips up
    // make files public
  }

}
//def jsonStr = new JsonBuilder( jsonClassArr ).toPrettyString()
//def jsonStr = new JsonBuilder( jsonClassArr ).toString()
def jsonStr = JsonOutput.prettyPrint(JsonOutput.toJson(jsonClassArr))
jsonStr = "cp = " + jsonStr;
//jsonStr = "cp = " + jsonStr.replaceAll('"', '\\\\"');
new File("../web/cp.json").withWriter { out -> out.write(jsonStr) };

def String proc(def cmd) {
  println "cmd: ${cmd}";
  def proc = cmd.execute();
  proc.waitFor();
  println "return code: ${proc.exitValue()}"
  println "stderr: ${proc.err.text}"
  String outStr = proc.in.text
  println "stdout: ${outStr}"
  return outStr
}

def getNewHandoutFileName(id, ht, hf) {
  if (hf != null && hf.indexOf('http') == -1) {
    def m = hf =~ /\.(.*)/
    def ext = m[0][1];
    println "ht: ${ht}"
    ht = ht.replaceAll(' ', '_');
    println "${id}-${ht}.${ext}"
    return "${id}-${ht}.${ext}"
  } else {
    return hf;
  }
}

def runVelocity(def templateFile, def outputFile, def data) {
  def writer = new BufferedWriter(new FileWriter(outputFile))
  Template template = Velocity.getTemplate(templateFile);
  def context = new VelocityContext();
  for (e in data) {
    println "${e.key}: ${e.value}"
    context.put(e.key, e.value);
    
  }
  template.merge(context, writer);
  writer.close();
}

def fileNewerThan(def origFileStr, def newFileStr, def updatedDate) {
  println "fileNewerThan: newFileStr: ${newFileStr} updatedDate: ${updatedDate}";
  def needToGen = true;

  def newFile = new File(newFileStr);
  println "newFile.exists(): ${newFile.exists()}"
  def origFile = new File(origFileStr);
  if (!origFile.exists()) {
    needToGen = false;
  } else if ((updatedDate == null || updatedDate.toCalendar().getTimeInMillis() < newFile.lastModified()) && newFile.exists() && newFile.lastModified() >= origFile.lastModified()) {
    needToGen = false  
  }

  println "needToGen: ${needToGen}"
  return needToGen;
}

def fileNewerThanAll(def folder2zipStr, def zipStr) {
  def retVal = true;
  def zipFile = new File(zipStr);

  if (zipFile.exists()) {
    retVal = false;
    def mostRecentMod = 0;
    for (f in FileUtils.listFiles(new File(folder2zipStr), null, true)) {
      if (f.lastModified() > mostRecentMod) {
        mostRecentMod = f.lastModified();
      }
    }
    if (mostRecentMod > zipFile.lastModified()) {
      retVal = true;
    }
  }

  return retVal;
}
