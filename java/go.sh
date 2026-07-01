#!/bin/bash
. ~/.bashrc
#flock -n go.lockfile bash -c "echo hello" || exit 1
# crontab
# */5 * * * * cd /mydev/course2web/java && flock -n go.lockfile ./go.sh > ./go.out


#while [ true ]
#do
  #sudo service ntp stop
  PD1=$(pwd)
  #cd ~/gdrive/catholic/tedesche/uploads/daily_homilies
  #drive pull
  cd $PD1
  export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
  #sudo ntpdate ntp.ubuntu.com
  date;

  # this is not preserving the timestamp
  #cp -puR /google_drive/catholic/tedesche/uploads/* ./orig
  #rsync -rt ~/gdrive/catholic/tedesche/uploads/daily_homilies ./orig
cmd.exe --% /c copy  'g:\My Drive\catholic\tedesche\uploads\daily_homilies\audio' 'C:\dev\daily_homilies\audio'
cmd.exe --% /c copy  'g:\My Drive\catholic\tedesche\uploads\daily_homilies\docs' 'C:\dev\daily_homilies\docs'
cmd.exe --% /c copy  'g:\My Drive\catholic\tedesche\uploads\misc\audio' 'C:\dev\misc\audio'
cmd.exe --% /c copy  'g:\My Drive\catholic\tedesche\uploads\st_joseph_novena\audio' 'C:\dev\st_joseph_novena\audio'
cmd.exe --% /c copy  'g:\My Drive\catholic\tedesche\uploads\magnificat_humanitas\audio' 'C:\dev\magnificat_humanitas\audio'
  rsync -rt /mnt/c/dev/daily_homilies/audio ./orig/daily_homilies
  rsync -rt /mnt/c/dev/daily_homilies/docs ./orig/daily_homilies
  rsync -rt /mnt/c/dev/misc/audio ./orig/misc
  rsync -rt /mnt/c/dev/st_joseph_novena/audio ./orig/st_joseph_novena
  rsync -rt /mnt/c/dev/magnificat_humanitas/audio ./orig/magnificat_humanitas
  #rsync -rt /google_drive/catholic/tedesche/uploads/Sunday_Homilies ./orig
  #rsync -rt /google_drive/catholic/tedesche/uploads/wednesday_night_talks ./orig
  #rsync -rt /google_drive/catholic/tedesche/uploads/adult_education ./orig

  # run groovy
  # ant groovy; 
  #groovy -cp 'lib/*' src/test.groovy
  mv lib/groovy/lib/groovy-1.7.11.jar  lib/groovy/lib/groovy-1.7.11.jar.bak 2> /dev/null
  groovy -cp 'lib/*' src/BackendIngestorAndTransformer.groovy
  # groovy -cp 'lib/*' src/test.groovy
  #groovy -v
  
  if [ $? -eq 0 ]; then
    date;
    s3cmd -P sync build/daily_homilies/ s3://www.catholicpatrimony.com/daily_homilies/
    s3cmd -P sync build/misc/ s3://www.catholicpatrimony.com/misc/
    s3cmd -P sync build/st_joseph_novena/ s3://www.catholicpatrimony.com/st_joseph_novena/
    s3cmd -P sync build/magnificat_humanitas/ s3://www.catholicpatrimony.com/magnificat_humanitas/
    #s3cmd -P sync build/Sunday_Homilies/ s3://www.catholicpatrimony.com/Sunday_Homilies/
    #s3cmd -P sync build/wednesday_night_talks/ s3://www.catholicpatrimony.com/wednesday_night_talks/
    #s3cmd -P sync build/adult_education/ s3://www.catholicpatrimony.com/adult_education/
    s3cmd sync --add-header=Cache-Control:no-cache -P --guess-mime-type ../web/cp.json s3://www.catholicpatrimony.com/
  else
    echo "failed - don't sync"
  fi
  date;

  # push latest to www.catholicpatrimony.com

  date;

#  sleep 1200;
#done

# when you change web stuff
#find ../web/ -name \*.js -o -name \*.html | xargs sed -i 's/cbp=......../cbp=20020704b/g'
#s3cmd -P sync ../web/ s3://www.catholicpatrimony.com/
